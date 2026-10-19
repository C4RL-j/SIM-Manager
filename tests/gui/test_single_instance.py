"""Private local activation never composes a second background application."""

from contextlib import redirect_stderr
import io
import tempfile
import uuid
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtNetwork import QLocalSocket

from test_desktop import DesktopCase
from sim_manager import app
from sim_manager.ui.single_instance import SingleInstanceGuard


class SingleInstanceTests(DesktopCase):
    def guard(self, name=None):
        if not hasattr(self, "lock_directory"):
            directory = tempfile.TemporaryDirectory()
            self.addCleanup(directory.cleanup)
            self.lock_directory = directory.name
        guard = SingleInstanceGuard(name=name or "SIMManager.Test." + uuid.uuid4().hex,
                                    lock_directory=self.lock_directory)
        self.addCleanup(guard.shutdown)
        return guard

    def test_second_instance_activates_first_then_lock_can_be_reacquired(self):
        first = self.guard()
        events = []
        first.activation_requested.connect(lambda: events.append("activate"))
        self.assertTrue(first.acquire_or_notify())
        self.assertTrue(first.acquire_or_notify())
        # A second real process has its own Python interpreter. A same-process
        # blocking writer can hold the GIL while this server needs it to accept,
        # so check its fixed notification here without a Python worker thread.
        second = self.guard(first._name)
        notification = MagicMock()
        notification.waitForConnected.return_value = True
        notification.write.return_value = 9
        notification.bytesToWrite.return_value = 9
        notification.waitForBytesWritten.return_value = True
        with patch("sim_manager.ui.single_instance.QLocalSocket", return_value=notification):
            self.assertFalse(second.acquire_or_notify())
        self.assertTrue(second.notified_existing)
        notification.connectToServer.assert_called_once_with(first._name)
        notification.write.assert_called_once_with(b"activate\n")
        notification.waitForBytesWritten.assert_called_once()
        notification.close.assert_called_once()

        # Exercise real local activation asynchronously, keeping the server's
        # event loop available instead of waiting in another Python thread.
        connection = QLocalSocket()
        self.addCleanup(connection.close)
        connection.connectToServer(first._name)
        self.assertTrue(connection.waitForConnected(300))
        self.assertEqual(connection.write(b"activate\n"), 9)
        connection.flush()
        self.wait_until(lambda: events == ["activate"])
        connection.close()
        first.shutdown()
        replacement = self.guard(first._name)
        self.assertTrue(replacement.acquire_or_notify())

    def test_only_fixed_activation_message_is_accepted_even_when_fragmented(self):
        guard = self.guard()
        self.assertTrue(guard.acquire_or_notify())
        events = []
        guard.activation_requested.connect(lambda: events.append("activate"))

        def client():
            connection = QLocalSocket()
            self.addCleanup(connection.close)
            connection.connectToServer(guard._name)
            self.assertTrue(connection.waitForConnected(300))
            self.wait_until(lambda: len(guard._clients) == 1)
            return connection

        bad = client()
        bad.write(b"execute something\n")
        bad.flush()
        self.wait_until(lambda: not guard._clients)
        self.assertEqual(events, [])
        good = client()
        good.write(b"acti")
        good.flush()
        self.wait_until(lambda: tuple(guard._clients.values()) == (b"acti",))
        self.assertEqual(events, [])
        good.write(b"vate\n")
        good.flush()
        self.wait_until(lambda: events == ["activate"] and not guard._clients)
        guard.shutdown()
        self.application.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_existing_instance_does_not_construct_services_window_or_second_event_loop(self):
        guard = MagicMock()
        guard.acquire_or_notify.return_value = False
        guard.notified_existing = True
        application = MagicMock()
        with patch.object(app, "create_application", return_value=application), \
                patch("sim_manager.ui.single_instance.SingleInstanceGuard", return_value=guard), \
                patch.object(app, "create_window") as compose:
            self.assertEqual(app.main([]), 0)
        compose.assert_not_called()
        application.exec.assert_not_called()

    def test_unavailable_activation_channel_reports_only_safe_static_error(self):
        guard = MagicMock()
        guard.acquire_or_notify.return_value = False
        guard.notified_existing = False
        error = io.StringIO()
        with patch.object(app, "create_application", return_value=MagicMock()), \
                patch("sim_manager.ui.single_instance.SingleInstanceGuard", return_value=guard), \
                patch.object(app, "create_window") as compose, redirect_stderr(error):
            self.assertEqual(app.main([]), 1)
        compose.assert_not_called()
        self.assertEqual(error.getvalue(), "SIM Manager could not open its desktop session.\n")
