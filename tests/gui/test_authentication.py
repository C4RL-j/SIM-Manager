"""Offline runtime sign-in flow; synthetic passwords never leave the process."""

from contextlib import redirect_stderr, redirect_stdout
import io
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLineEdit, QToolButton

from sim_manager.models import DeviceIssue, DeviceState, IssueCode
from sim_manager.services.device import AuthenticationError, AuthenticationFailure
from sim_manager.ui.authentication import RouterSignInDialog
from sim_manager.ui.refresh import _RuntimeCredentials
from sim_manager.storage.windows_credentials import RememberedD2Login

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
    def dialog(self, **kwargs):
        dialog = RouterSignInDialog("https://192.168.1.1", self.window(), **kwargs)
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
                dialog.password_visibility_action.trigger()
                if action == "escape":
                    QTest.keyClick(dialog, Qt.Key.Key_Escape)
                else:
                    getattr(dialog, action)()
                self.assertEqual(dialog.password_input.text(), "")
                self.assertEqual(dialog.username_input.text(), "")
                self.assertFalse(dialog.password_input.isUndoAvailable())
                self.assertFalse(dialog.username_input.isUndoAvailable())
                self.assertEqual(dialog.password_input.echoMode(), QLineEdit.EchoMode.Password)
                self.assertFalse(dialog.password_visibility_action.isChecked())
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

    def test_eye_toggles_current_password_and_accessibility_without_submission_or_clipboard(self):
        dialog = self.dialog()
        dialog.username_input.setText(USERNAME)
        dialog.password_input.setText(PASSWORD)
        submitted = []
        dialog.credentials_submitted.connect(lambda username, password: submitted.append(True))
        clipboard_type = type(self.application.clipboard())
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output), patch.object(
            clipboard_type, "setText", side_effect=AssertionError("Clipboard writes forbidden"),
        ), patch.object(clipboard_type, "clear", side_effect=AssertionError("Clipboard writes forbidden")):
            self.assertFalse(dialog.password_visibility_action.isChecked())
            self.assertFalse(dialog.password_visibility_action.icon().isNull())
            dialog.password_visibility_action.trigger()
            self.assertEqual(dialog.password_input.echoMode(), QLineEdit.EchoMode.Normal)
            self.assertEqual(dialog.password_input.text(), PASSWORD)
            self.assertEqual(dialog.password_visibility_action.text(), "Hide password")
            eye = next(button for button in dialog.password_input.findChildren(QToolButton)
                       if button.defaultAction() is dialog.password_visibility_action)
            self.assertEqual(eye.accessibleName(), "Hide password")
            dialog.password_visibility_action.trigger()
            self.assertEqual(dialog.password_input.echoMode(), QLineEdit.EchoMode.Password)
            self.assertEqual(dialog.password_input.text(), PASSWORD)
            self.assertEqual(dialog.password_visibility_action.text(), "Show password")
            self.assertEqual(eye.accessibleName(), "Show password")
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(submitted, [])
        self.assertEqual(dialog.username_input.text(), USERNAME)

    def test_remember_is_opt_in_and_submit_snapshots_choice_before_cleared_handoff(self):
        dialog = self.dialog()
        self.assertFalse(dialog.remember_checkbox.isChecked())
        self.assertTrue(dialog.remember_checkbox.isEnabled())
        self.assertFalse(dialog.remember_requested)
        self.assertFalse(dialog.forget_button.isVisible())
        self.assertIn("D2 router admin login", self.displayed_text(dialog))
        self.assertIn("separate from your DITO account", self.displayed_text(dialog))
        dialog.username_input.setText(USERNAME)
        dialog.password_input.setText(PASSWORD)
        dialog.remember_checkbox.setChecked(True)
        dialog.password_visibility_action.trigger()
        observed = []
        dialog.credentials_submitted.connect(lambda username, password: observed.append((
            username == USERNAME, password == PASSWORD, dialog.remember_requested,
            dialog.username_input.text() == "", dialog.password_input.text() == "",
            dialog.password_input.echoMode() == QLineEdit.EchoMode.Password,
        )))
        dialog.accept()
        self.assertEqual(observed, [(True, True, True, True, True, True)])
        self.assertNotIn(PASSWORD, repr(dialog) + self.displayed_text(dialog))

    def test_only_typed_remembered_model_prefills_inputs_and_remains_masked(self):
        dialog = self.dialog(remembered_login=RememberedD2Login(USERNAME, PASSWORD))
        self.assertEqual(dialog.username_input.text(), USERNAME)
        self.assertEqual(dialog.password_input.text(), PASSWORD)
        self.assertEqual(dialog.password_input.echoMode(), QLineEdit.EchoMode.Password)
        self.assertTrue(dialog.remember_checkbox.isChecked())
        self.assertTrue(dialog.forget_button.isVisible())
        other = self.dialog(remembered_login=SimpleNamespace(username=USERNAME, password=PASSWORD))
        self.assertEqual(other.username_input.text(), "")
        self.assertEqual(other.password_input.text(), "")
        self.assertFalse(other.remember_checkbox.isChecked())
        self.assertFalse(other.forget_button.isVisible())

    def test_forget_clears_inputs_undo_visibility_and_choice_before_secret_free_signal(self):
        dialog = self.dialog(remembered_login=RememberedD2Login(USERNAME, PASSWORD))
        dialog.password_visibility_action.trigger()
        observed = []
        dialog.forget_requested.connect(lambda: observed.append((
            dialog.username_input.text() == "", dialog.password_input.text() == "",
            dialog.password_input.echoMode() == QLineEdit.EchoMode.Password,
            dialog.remember_checkbox.isChecked(), dialog.remember_requested,
            dialog.forget_button.isVisible(),
        )))
        dialog.forget_button.click()
        self.assertEqual(observed, [(True, True, True, False, False, False)])
        self.assertFalse(dialog.username_input.isUndoAvailable())
        self.assertFalse(dialog.password_input.isUndoAvailable())
        self.assertTrue(dialog.isVisible())

    def test_unavailable_remember_storage_keeps_runtime_login_and_cannot_request_save(self):
        dialog = self.dialog(remember_available=False)
        self.assertFalse(dialog.remember_checkbox.isEnabled())
        self.assertFalse(dialog.remember_checkbox.isChecked())
        self.assertIn("unavailable", dialog.storage_note.text())
        # A programmatically checked disabled control must still not save.
        dialog.remember_checkbox.setChecked(True)
        dialog.username_input.setText(USERNAME)
        dialog.password_input.setText(PASSWORD)
        requested = []
        dialog.credentials_submitted.connect(lambda username, password: requested.append(dialog.remember_requested))
        dialog.accept()
        self.assertEqual(requested, [False])

    def test_external_forget_clears_autofill_without_recursive_storage_signal(self):
        dialog = self.dialog(remembered_login=RememberedD2Login(USERNAME, PASSWORD))
        dialog.password_visibility_action.trigger()
        requests = []
        dialog.forget_requested.connect(lambda: requests.append(True))
        dialog.clear_autofill()
        self.assertEqual(requests, [])
        self.assertEqual(dialog.username_input.text(), "")
        self.assertEqual(dialog.password_input.text(), "")
        self.assertEqual(dialog.password_input.echoMode(), QLineEdit.EchoMode.Password)
        self.assertFalse(dialog.remember_checkbox.isChecked())
        self.assertFalse(dialog.forget_button.isVisible())

    def test_alphanumeric_router_usernames_are_accepted_without_numeric_validator(self):
        for username in ("admin7", "D2Admin42"):
            with self.subTest(username=username):
                dialog = self.dialog()
                self.assertIsNone(dialog.username_input.validator())
                dialog.username_input.setText(username)
                dialog.password_input.setText(PASSWORD)
                submitted = []
                dialog.credentials_submitted.connect(lambda value, password: submitted.append(value))
                dialog.accept()
                self.assertEqual(submitted, [username])

    def test_raw_storage_notice_is_redacted_and_cancel_does_not_remember(self):
        dialog = self.dialog()
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            dialog.set_storage_notice(PASSWORD)
            dialog.username_input.setText(USERNAME)
            dialog.password_input.setText(PASSWORD)
            dialog.remember_checkbox.setChecked(True)
            dialog.reject()
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn(PASSWORD, dialog.storage_note.text() + repr(dialog))
        self.assertFalse(dialog.remember_requested)
        self.assertEqual(dialog.username_input.text(), "")
        self.assertEqual(dialog.password_input.text(), "")


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
        for page in range(5):
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
        window.navigation.setCurrentRow(4)
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
