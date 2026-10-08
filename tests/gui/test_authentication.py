"""Offline runtime sign-in flow; synthetic passwords never leave the process."""

from contextlib import redirect_stderr, redirect_stdout
import io
import threading
import time
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLineEdit

from sim_manager.models import DeviceIssue, DeviceState, IssueCode
from sim_manager.services.device import AuthenticationError, AuthenticationFailure
from sim_manager.ui.authentication import RouterSignInDialog
from sim_manager.ui.refresh import _RuntimeCredentials

from test_desktop import DesktopCase, known_snapshot


PASSWORD = "SYNTHETIC_RUNTIME_PASSWORD"
USERNAME = "SYNTHETIC_RUNTIME_USER"


def authentication_required():
    return DeviceState(errors=(DeviceIssue("wireless", IssueCode.AUTHENTICATION_REQUIRED),))


class AuthenticationProvider:
    """Legitimate sign-in + read contract, with no sockets or stored password."""

    is_demo = False
    router_address = "https://192.168.1.1"

    def __init__(self, *, error=None, blocked=False):
        self.authenticated = False
        self.error = error
        self.blocked = blocked
        self.calls = []
        self.auth_calls = []
        self.password_matches = []
        self.username_matches = []
        self.started = threading.Event()
        self.finished = threading.Event()
        self.release = threading.Event()

    def get_device_state(self, *, stop_event=None):
        self.calls.append((threading.get_ident(), stop_event))
        return known_snapshot() if self.authenticated else authentication_required()

    def authenticate(self, password, *, username, stop_event=None):
        self.auth_calls.append((threading.get_ident(), stop_event))
        self.password_matches.append(password == PASSWORD)
        self.username_matches.append(username == USERNAME)
        self.started.set()
        try:
            deadline = time.monotonic() + 2.0
            while self.blocked and not self.release.is_set():
                if stop_event is not None and stop_event.is_set():
                    raise AuthenticationError(AuthenticationFailure.CANCELLED)
                if time.monotonic() >= deadline:
                    raise AuthenticationError(AuthenticationFailure.TIMEOUT)
                self.release.wait(0.005)
            if self.error is not None:
                raise self.error
            self.authenticated = True
            # Match the live service contract: successful sign-in already
            # includes the fresh read, without a second GUI worker or prompt.
            return self.get_device_state(stop_event=stop_event)
        finally:
            self.finished.set()


class SignInDialogTests(DesktopCase):
    def dialog(self):
        dialog = RouterSignInDialog("https://192.168.1.1", self.window())
        dialog.show()
        self.addCleanup(dialog.reject)
        return dialog

    def test_password_is_masked_and_empty_submission_remains_in_dialog(self):
        dialog = self.dialog()
        submitted = []
        dialog.credentials_submitted.connect(lambda username, password: submitted.append((username, password)))
        self.assertEqual(dialog.password_input.echoMode(), QLineEdit.EchoMode.Password)
        self.assertEqual(dialog.password_input.accessibleName(), "Router password")
        self.assertEqual(dialog.password_input.text(), "")
        self.assertEqual(dialog.username_input.text(), "")
        QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)
        self.assertTrue(dialog.isVisible())
        self.assertEqual(dialog.validation_label.text(), "Enter the router username.")
        dialog.username_input.setText(USERNAME)
        QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.StandardButton.Ok), Qt.MouseButton.LeftButton)
        self.assertEqual(dialog.validation_label.text(), "Enter the router password.")
        self.assertEqual(submitted, [])

    def test_submit_preserves_password_whitespace_and_clears_before_signal(self):
        for password in ("  synthetic password  ", "   "):
            with self.subTest(spaces_only=password.isspace()):
                dialog = self.dialog()
                submitted = []
                dialog.credentials_submitted.connect(
                    lambda username, value: submitted.append((username, value, dialog.username_input.text(), dialog.password_input.text())),
                )
                dialog.username_input.setText("  synthetic username  ")
                dialog.password_input.setText(password)
                dialog.accept()
                self.assertEqual(submitted, [("  synthetic username  ", password, "", "")])
                self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
                self.assertFalse(dialog.password_input.isUndoAvailable())
                self.assertFalse(dialog.username_input.isUndoAvailable())
                dialog.password_input.undo()
                self.assertEqual(dialog.password_input.text(), "")

    def test_reject_escape_and_close_clear_input_and_undo_history(self):
        for action in ("reject", "escape", "close"):
            with self.subTest(action=action):
                dialog = self.dialog()
                submitted = []
                dialog.credentials_submitted.connect(lambda username, password: submitted.append((username, password)))
                dialog.username_input.setText(USERNAME)
                dialog.password_input.setText(PASSWORD)
                if action == "escape":
                    QTest.keyClick(dialog, Qt.Key.Key_Escape)
                else:
                    getattr(dialog, action)()
                self.assertEqual(dialog.password_input.text(), "")
                self.assertEqual(dialog.username_input.text(), "")
                self.assertFalse(dialog.password_input.isUndoAvailable())
                self.assertFalse(dialog.username_input.isUndoAvailable())
                self.assertEqual(submitted, [])
                self.assertNotIn(PASSWORD, repr(dialog))

    def test_runtime_credentials_handoff_is_opaque_and_single_use(self):
        credential = _RuntimeCredentials(USERNAME, PASSWORD)
        self.assertNotIn(PASSWORD, repr(credential))
        self.assertNotIn(PASSWORD, str(credential))
        self.assertNotIn(USERNAME, repr(credential))
        self.assertEqual(credential.take(), (USERNAME, PASSWORD))
        self.assertEqual(credential.take(), ("", ""))
        credential.clear()

    def test_blank_and_whitespace_username_is_rejected_without_trimming_valid_input(self):
        dialog = self.dialog()
        submitted = []
        dialog.credentials_submitted.connect(lambda username, password: submitted.append((username, password)))
        dialog.password_input.setText(PASSWORD)
        for username in ("", "   ", "\t"):
            dialog.username_input.setText(username)
            dialog.accept()
            self.assertTrue(dialog.isVisible())
            self.assertEqual(dialog.validation_label.text(), "Enter the router username.")
            self.assertEqual(submitted, [])
        dialog.username_input.setText("  synthetic username  ")
        dialog.accept()
        self.assertEqual(submitted, [("  synthetic username  ", PASSWORD)])


class AuthenticationFlowTests(DesktopCase):
    def auth_provider(self, **kwargs):
        provider = AuthenticationProvider(**kwargs)
        self.providers.append(provider)
        return provider

    def ready_window(self, provider):
        window = self.window(provider)
        window.render_snapshot(authentication_required())
        return window

    def submit(self, window):
        self.assertTrue(window.open_sign_in())
        dialog = window._sign_in_dialog
        # A rejected attempt must never populate the next runtime dialog.
        self.assertEqual(dialog.password_input.text(), "")
        self.assertEqual(dialog.username_input.text(), "")
        self.assertEqual(dialog.password_input.echoMode(), QLineEdit.EchoMode.Password)
        dialog.username_input.setText(USERNAME)
        dialog.password_input.setText(PASSWORD)
        dialog.accept()
        self.assertEqual(dialog.password_input.text(), "")
        self.assertEqual(dialog.username_input.text(), "")
        self.assertIsNone(window._sign_in_dialog)

    def test_authentication_required_offers_sign_in_without_automatic_dialogs(self):
        provider = self.auth_provider()
        window = self.ready_window(provider)
        self.assertEqual(window.status_label.text(), "Authentication required")
        self.assertTrue(window.sign_in_button.isVisible())
        self.assertFalse(window.live_label.isVisible())
        self.assertIsNone(window._sign_in_dialog)
        self.assertEqual(window.settings_page.router_address_label.text(), provider.router_address)
        for _ in range(2):
            self.assertTrue(window.start_refresh())
            self.wait_until(lambda: not window.refresh_controller.busy)
            self.assertIsNone(window._sign_in_dialog)
        self.assertEqual(provider.auth_calls, [])

    def test_sign_in_opens_once_and_blocks_refresh_until_dismissed(self):
        provider = self.auth_provider()
        window = self.ready_window(provider)
        self.assertTrue(window.open_sign_in())
        dialog = window._sign_in_dialog
        self.assertFalse(window.open_sign_in())
        self.assertIs(window._sign_in_dialog, dialog)
        self.assertFalse(window.start_refresh())
        self.assertFalse(window.sign_in_button.isEnabled())
        dialog.password_input.setText(PASSWORD)
        dialog.username_input.setText(USERNAME)
        dialog.reject()
        self.assertEqual(dialog.password_input.text(), "")
        self.assertEqual(dialog.username_input.text(), "")
        self.assertIsNone(window._sign_in_dialog)
        self.assertTrue(window.sign_in_button.isEnabled())
        self.assertEqual(provider.auth_calls, [])
        self.assertEqual(provider.calls, [])

    def test_successful_login_reads_snapshot_off_thread_and_displays_live(self):
        provider = self.auth_provider(blocked=True)
        window = self.ready_window(provider)
        self.submit(window)
        self.wait_until(provider.started.is_set)
        self.assertEqual(window.status_label.text(), "Signing in…")
        self.assertFalse(window.sign_in_button.isEnabled())
        self.assertFalse(window.start_refresh())
        self.assertFalse(window.open_sign_in())
        self.assertFalse(window.refresh_controller.authenticate(PASSWORD, username=USERNAME))
        self.assertNotEqual(provider.auth_calls[0][0], threading.get_ident())
        provider.release.set()
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertEqual(len(provider.auth_calls), 1)
        self.assertEqual(provider.password_matches, [True])
        self.assertEqual(provider.username_matches, [True])
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(provider.calls[0][0], provider.auth_calls[0][0])
        self.assertEqual(self.values(window)["rsrp"], "-91")
        self.assertEqual(self.values(window)["carrier"], "Unknown")
        self.assertEqual(window.status_label.text(), "● Router data available")
        self.assertTrue(window.live_label.isVisible())
        self.assertFalse(window.sign_in_button.isVisible())
        for page in range(3):
            window.navigation.setCurrentRow(page)
            self.assertTrue(window.live_label.isVisible())
        self.assertNotIn(PASSWORD, self.displayed_text(window))

    def test_closed_authentication_failures_are_safe_and_allow_retry(self):
        messages = {
            AuthenticationFailure.REJECTED: "Authentication rejected",
            AuthenticationFailure.MALFORMED: "Malformed authentication response",
            AuthenticationFailure.TIMEOUT: "Router timed out",
            AuthenticationFailure.UNREACHABLE: "Router unreachable",
            AuthenticationFailure.CONNECTION: "Router connection problem",
            AuthenticationFailure.CANCELLED: "Sign-in cancelled",
        }
        for code, message in messages.items():
            with self.subTest(code=code):
                error = AuthenticationError(code)
                # Even a badly injected exception carrying private args must
                # be classified only by its closed code, never formatted.
                error.args = (PASSWORD,)
                provider = self.auth_provider(error=error)
                window = self.ready_window(provider)
                output = io.StringIO()
                with redirect_stdout(output), redirect_stderr(output):
                    self.submit(window)
                    self.wait_until(lambda: not window.refresh_controller.busy)
                self.assertEqual(window.status_label.text(), message)
                self.assertTrue(window.sign_in_button.isVisible())
                self.assertTrue(window.sign_in_button.isEnabled())
                self.assertFalse(window.live_label.isVisible())
                self.assertNotIn(PASSWORD, output.getvalue() + self.displayed_text(window))
                self.assertEqual(provider.calls, [])
                self.assertEqual(len(provider.auth_calls), 1)
                provider.error = None
                self.submit(window)
                self.wait_until(lambda: not window.refresh_controller.busy)
                self.assertTrue(window.live_label.isVisible())

    def test_expired_session_hides_live_badge_and_allows_explicit_relogin(self):
        provider = self.auth_provider()
        window = self.ready_window(provider)
        self.submit(window)
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertTrue(window.live_label.isVisible())
        provider.authenticated = False
        window.start_refresh()
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertEqual(window.status_label.text(), "Authentication required")
        self.assertFalse(window.live_label.isVisible())
        self.assertTrue(window.sign_in_button.isVisible())
        self.assertIsNone(window._sign_in_dialog)
        self.assertEqual(len(provider.auth_calls), 1)
        self.submit(window)
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertEqual(len(provider.auth_calls), 2)
        self.assertTrue(window.live_label.isVisible())

    def test_partial_live_snapshot_remains_visible_after_successful_sign_in(self):
        provider = self.auth_provider()
        window = self.ready_window(provider)
        with patch.object(provider, "get_device_state", return_value=known_snapshot(
            errors=(DeviceIssue("wireless", IssueCode.UNAVAILABLE),), partial=True,
        )):
            self.submit(window)
            self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertTrue(window.live_label.isVisible())
        self.assertEqual(self.values(window)["rsrp"], "-91")
        self.assertEqual(self.values(window)["router_status"], "Partial data")

    def test_cancel_sign_in_uses_shared_event_and_leaves_explicit_retry(self):
        provider = self.auth_provider(blocked=True)
        window = self.ready_window(provider)
        self.submit(window)
        self.wait_until(provider.started.is_set)
        stop = provider.auth_calls[0][1]
        window.navigation.setCurrentRow(2)
        self.assertTrue(window.cancel_button.isVisible())
        QTest.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertTrue(stop.is_set())
        self.assertTrue(provider.finished.is_set())
        self.assertEqual(window.status_label.text(), "Sign-in cancelled")
        self.assertTrue(window.sign_in_button.isEnabled())
        self.assertEqual(provider.calls, [])

    def test_close_cancels_and_joins_sign_in_worker_without_late_ui_updates(self):
        provider = self.auth_provider(blocked=True)
        window = self.ready_window(provider)
        self.submit(window)
        self.wait_until(provider.started.is_set)
        worker_id, stop = provider.auth_calls[0]
        before = self.values(window)
        started = time.monotonic()
        window.close()
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertTrue(stop.is_set())
        self.assertTrue(provider.finished.is_set())
        self.assertFalse(any(worker.ident == worker_id for worker in threading.enumerate()))
        self.application.processEvents()
        self.assertEqual(self.values(window), before)
        self.assertFalse(window.open_sign_in())
        self.assertFalse(window.refresh_controller.authenticate(PASSWORD, username=USERNAME))

    def test_closing_window_with_open_dialog_discards_unsubmitted_password(self):
        provider = self.auth_provider()
        window = self.ready_window(provider)
        window.open_sign_in()
        dialog = window._sign_in_dialog
        dialog.username_input.setText(USERNAME)
        dialog.password_input.setText(PASSWORD)
        window.close()
        self.assertEqual(dialog.password_input.text(), "")
        self.assertEqual(dialog.username_input.text(), "")
        self.assertIsNone(window._sign_in_dialog)
        self.assertEqual(provider.auth_calls, [])

    def test_sign_in_thread_start_failure_is_safe_and_retryable(self):
        provider = self.auth_provider()
        window = self.ready_window(provider)
        with patch("sim_manager.ui.refresh.Thread.start", side_effect=RuntimeError(PASSWORD)):
            self.submit(window)
        self.assertFalse(window.refresh_controller.busy)
        self.assertEqual(window.status_label.text(), "Unknown error")
        self.assertTrue(window.sign_in_button.isEnabled())
        self.assertEqual(provider.auth_calls, [])
        self.assertNotIn(PASSWORD, self.displayed_text(window))

    def test_shutdown_closes_service_once_after_requesting_cancellation(self):
        provider = self.auth_provider(blocked=True)
        window = self.ready_window(provider)
        self.submit(window)
        self.wait_until(provider.started.is_set)
        calls = []

        def close_provider():
            calls.append(provider.auth_calls[0][1].is_set())
            raise RuntimeError(PASSWORD)

        with patch.object(provider, "close", close_provider, create=True):
            window.close()
            self.assertTrue(window.refresh_controller.shutdown())
        self.assertEqual(calls, [True])
        self.assertTrue(provider.finished.is_set())
        self.assertNotIn(PASSWORD, self.displayed_text(window))

    def test_demo_never_offers_or_executes_sign_in_even_with_capable_provider(self):
        provider = self.auth_provider()
        window = self.window(provider, demo=True)
        window.render_snapshot(authentication_required())
        self.assertFalse(window.sign_in_button.isVisible())
        self.assertFalse(window.open_sign_in())
        self.assertFalse(window.refresh_controller.authenticate(PASSWORD, username=USERNAME))
        self.assertTrue(window.demo_label.isVisible())
        self.assertFalse(window.live_label.isVisible())
        self.assertEqual(provider.auth_calls, [])

    def test_refresh_only_provider_and_invalid_password_cannot_start_authentication(self):
        window = self.ready_window(self.provider())
        self.assertFalse(window.sign_in_button.isVisible())
        self.assertFalse(window.open_sign_in())
        self.assertFalse(window.refresh_controller.authenticate(PASSWORD, username=USERNAME))
        provider = self.auth_provider()
        window = self.ready_window(provider)
        for password in ("", None, b"synthetic"):
            self.assertFalse(window.refresh_controller.authenticate(password, username=USERNAME))
        for username in ("", "   ", None, b"synthetic"):
            self.assertFalse(window.refresh_controller.authenticate(PASSWORD, username=username))
        self.assertEqual(provider.auth_calls, [])
