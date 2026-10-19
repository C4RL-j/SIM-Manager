"""Synthetic owned message dialogs; no live inbox or system clipboard writes."""

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import isValid

from sim_manager.message_models import Message
from sim_manager.ui.message_details import MessageDetailsDialog


class Clipboard:
    def __init__(self):
        self.writes = []
        self.reads = self.clears = 0

    def setText(self, value):
        self.writes.append(value)

    def text(self):
        self.reads += 1
        raise AssertionError("No automatic clipboard inspection")

    def clear(self):
        self.clears += 1
        raise AssertionError("No automatic clipboard clearing")


class MessageDetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        cls.application.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.owner = QWidget()
        self.owner.resize(840, 600)
        self.owner.show()
        self.dialogs = []
        self.clipboard = Clipboard()
        self.clipboard_patch = patch.object(QApplication, "clipboard", return_value=self.clipboard)
        self.clipboard_patch.start()

    def tearDown(self):
        for dialog in self.dialogs:
            if isValid(dialog):
                dialog.close()
        if isValid(self.owner):
            self.owner.close()
            self.owner.deleteLater()
        self.flush_deletes()
        self.clipboard_patch.stop()

    def flush_deletes(self):
        for _ in range(3):
            self.application.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def opened(self, message):
        dialog = MessageDetailsDialog(message, self.owner)
        self.dialogs.append(dialog)
        dialog.show()
        self.application.processEvents()
        return dialog

    @staticmethod
    def cleared(dialog):
        return (dialog.sender_label.text() == "", dialog.timestamp_label.text() == "",
                dialog.timestamp_label.toolTip() == "", dialog.content_view.toPlainText() == "",
                not dialog.copy_button.isEnabled(), dialog._message is None)

    def test_full_plaintext_owned_modeless_dialog_copies_body_only_on_explicit_click(self):
        message = Message(sender="<b>Synthetic sender</b>", timestamp="2026-10-18 10:32:00",
                          body="<b>Synthetic body</b>\nhttps://example.invalid/plain-text")
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level="DEBUG"):
            dialog = self.opened(message)
            self.assertIs(dialog.parentWidget(), self.owner)
            self.assertEqual(dialog.windowModality(), Qt.WindowModality.NonModal)
            self.assertFalse(dialog.isModal())
            self.assertEqual(dialog.windowTitle(), "Message Details")
            self.assertEqual(dialog.sender_label.text(), message.sender)
            self.assertEqual(dialog.sender_label.textFormat(), Qt.TextFormat.PlainText)
            self.assertEqual(dialog.timestamp_label.textFormat(), Qt.TextFormat.PlainText)
            self.assertEqual(dialog.timestamp_label.text(), "Oct 18, 2026 · 10:32 AM")
            self.assertEqual(dialog.timestamp_label.toolTip(), message.timestamp)
            self.assertEqual(dialog.content_view.toPlainText(), message.body)
            self.assertTrue(dialog.content_view.isReadOnly())
            self.assertEqual(self.clipboard.writes, [])
            self.assertEqual(dialog.copy_button.text(), "Copy Message")
            dialog.copy_button.click()
            self.assertEqual(self.clipboard.writes, [message.body])
            finished = []
            dialog.finished.connect(lambda result: finished.append(self.cleared(dialog)))
            dialog.close_button.click()
            self.assertEqual(finished, [(True,) * 6])
            self.assertEqual(self.clipboard.writes, [message.body])
        self.assertEqual(output.getvalue(), "")
        self.assertEqual((self.clipboard.reads, self.clipboard.clears), (0, 0))
        self.flush_deletes()
        self.assertFalse(isValid(dialog))

    def test_escape_window_close_and_explicit_reset_clear_private_content_idempotently(self):
        for action in ("escape", "window-close", "reset"):
            dialog = self.opened(Message(sender="Synthetic", timestamp="Synthetic router time", body="Synthetic private body"))
            finished = []
            dialog.finished.connect(lambda result, current=dialog: finished.append(self.cleared(current)))
            if action == "escape":
                QTest.keyClick(dialog, Qt.Key.Key_Escape)
            else:
                if action == "reset":
                    dialog.clear_private_content()
                    dialog.clear_private_content()
                    self.assertEqual(self.cleared(dialog), (True,) * 6)
                    dialog.copy_button.click()
                dialog.close()
            self.assertEqual(finished, [(True,) * 6])
            self.flush_deletes()
            self.assertFalse(isValid(dialog))
        self.assertEqual(self.clipboard.writes, [])
        self.assertEqual((self.clipboard.reads, self.clipboard.clears), (0, 0))

    def test_long_message_wraps_scrolls_and_initial_geometry_stays_on_owner_screen(self):
        available = self.owner.screen().availableGeometry()
        self.owner.move(available.right() - 30, available.bottom() - 30)
        body = ("Synthetic paragraph " + "W" * 240 + "\n") * 80
        dialog = self.opened(Message(sender="Synthetic sender", timestamp="Unverified time zone", body=body))
        self.assertEqual(dialog.timestamp_label.text(), "Unverified time zone")
        self.assertTrue(available.contains(dialog.frameGeometry()))
        for width, height in ((400, 240), (640, 300)):
            dialog.resize(width, height)
            self.application.processEvents()
            self.assertEqual(dialog.content_view.toPlainText(), body)
            self.assertGreater(dialog.content_view.verticalScrollBar().maximum(), 0)
            self.assertEqual(dialog.content_view.horizontalScrollBar().maximum(), 0)
            self.assertTrue(dialog.copy_button.isVisible())
            self.assertTrue(dialog.close_button.isVisible())
            self.assertGreater(dialog.content_view.height(), 0)
        original = dialog.content_view.toPlainText()
        QTest.keyClicks(dialog.content_view, "Synthetic attempted edit")
        self.assertEqual(dialog.content_view.toPlainText(), original)

    def test_clipboard_failure_is_private_and_owner_disposal_clears_before_destruction(self):
        dialog = self.opened(Message(sender="Synthetic sender", timestamp="Synthetic time", body="Synthetic body"))
        output = StringIO()
        with patch.object(self.clipboard, "setText", side_effect=RuntimeError("SYNTHETIC_PRIVATE_CLIPBOARD")):
            with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level="DEBUG"):
                dialog.copy_button.click()
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("Synthetic body", repr(dialog))
        disposed = []
        self.owner.destroyed.connect(lambda: disposed.append(self.cleared(dialog)))
        self.owner.deleteLater()
        self.flush_deletes()
        self.assertEqual(disposed, [(True,) * 6])
        self.assertFalse(isValid(dialog))
        self.assertEqual((self.clipboard.reads, self.clipboard.clears), (0, 0))


if __name__ == "__main__":
    unittest.main()
