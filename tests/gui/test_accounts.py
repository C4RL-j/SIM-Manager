"""Synthetic account GUI/composition checks; never load a carrier website."""

from contextlib import redirect_stderr, redirect_stdout
import io
from unittest.mock import patch

from test_desktop import DesktopCase, active_dito_profiles
from test_messages import ControlledMessageProvider
from sim_manager import app
from sim_manager.account_models import AccountPhase, AccountState, AuthEvent
from sim_manager.message_models import Message, MessageInbox
from sim_manager.services.accounts import DemoAccountService, DitoAccountService
from sim_manager.ui.main_window import MainWindow


class SyntheticBrowser:
    def __init__(self):
        self.callback = None
        self.closed = False
        self.opened = 0
        self.shown = 0

    def open(self, callback):
        self.callback = callback
        self.opened += 1

    def show(self):
        self.shown += 1

    def close(self):
        self.closed = True


class AccountGuiTests(DesktopCase):
    def account_window(self, *, service=None, demo=False, messages=None):
        profiles, snapshot = active_dito_profiles(demo=demo)
        window = MainWindow(self.provider(), demo=demo, message_provider=messages,
                            account_service=service, sim_profiles=profiles)
        self.windows.append(window)
        window.show()
        window.render_snapshot(snapshot)
        window.navigation.setCurrentRow(1)
        return window

    def connected_service(self):
        browser = SyntheticBrowser()
        service = DitoAccountService(lambda: browser)
        return service, browser

    def test_connect_success_disconnect_and_fresh_sign_in_states(self):
        service, browser = self.connected_service()
        window = self.account_window(service=service)
        controls = window.sims_page.account_controls
        self.assertEqual(controls.status_label.text(), "Not connected")
        self.assertEqual(browser.opened, 0)
        self.assertFalse(controls.disconnect_button.isEnabled())
        controls.connect_button.click()
        self.assertEqual(controls.status_label.text(), "Sign in with DITO")
        self.assertEqual(browser.opened, 1)
        self.assertEqual(controls.disconnect_button.text(), "Cancel")
        controls.connect_button.click()
        self.assertEqual(browser.opened, 1)
        self.assertEqual(browser.shown, 1)
        browser.callback(AuthEvent.AUTHENTICATED)
        self.assertEqual(controls.status_label.text(), "Connected")
        self.assertFalse(controls.connect_button.isEnabled())
        controls.disconnect_button.click()
        self.assertTrue(browser.closed)
        self.assertEqual(controls.status_label.text(), "Not connected")

    def test_expired_session_offers_explicit_reconnect(self):
        service, browser = self.connected_service()
        window = self.account_window(service=service)
        controls = window.sims_page.account_controls
        controls.connect_button.click()
        browser.callback(AuthEvent.AUTHENTICATED)
        browser.callback(AuthEvent.EXPIRED)
        self.assertEqual(controls.status_label.text(), "Session expired")
        self.assertTrue(controls.connect_button.isEnabled())
        self.assertTrue(browser.closed)
        self.assertEqual(browser.opened, 1)

    def test_rejected_login_stays_user_controlled_and_cancel_ignores_late_success(self):
        service, browser = self.connected_service()
        window = self.account_window(service=service)
        controls = window.sims_page.account_controls
        controls.connect_button.click()
        browser.callback(AuthEvent.REJECTED)
        self.assertIn("not accepted", controls.detail_label.text())
        self.assertEqual(service.state.phase, AccountPhase.CONNECTING)
        controls.disconnect_button.click()
        browser.callback(AuthEvent.AUTHENTICATED)
        self.assertEqual(controls.status_label.text(), "Not connected")
        self.assertIn("cancelled", controls.detail_label.text())
        self.assertTrue(browser.closed)

    def test_explicit_copy_only_and_private_clipboard_clears_on_disconnect(self):
        service, browser = self.connected_service()
        window = self.account_window(service=service)
        controls = window.sims_page.account_controls
        self.application.clipboard().setText("Synthetic prior clipboard")
        controls.connect_button.click()
        controls.offer_otp(MessageInbox((Message(sender="DITO", body="123456 is your authentication code."),)))
        self.assertTrue(controls.otp_copy_button.isVisible())
        self.assertEqual(self.application.clipboard().text(), "Synthetic prior clipboard")
        self.assertNotIn("123456", self.displayed_text(controls))
        controls.otp_copy_button.click()
        self.assertEqual(self.application.clipboard().text(), "123456")
        self.assertEqual(browser.opened, 1)
        self.assertEqual(service.state.phase, AccountPhase.CONNECTING)
        controls.disconnect_button.click()
        self.assertEqual(self.application.clipboard().text(), "")
        self.assertFalse(controls.otp_copy_button.isVisible())

    def test_clipboard_changed_by_user_is_preserved_on_close(self):
        service, browser = self.connected_service()
        window = self.account_window(service=service)
        controls = window.sims_page.account_controls
        controls.connect_button.click()
        controls.offer_otp(MessageInbox((Message(sender="DITO", body="123456 is your authentication code."),)))
        controls.otp_copy_button.click()
        self.application.clipboard().setText("Synthetic user clipboard")
        window.close()
        self.assertEqual(self.application.clipboard().text(), "Synthetic user clipboard")
        self.assertTrue(browser.closed)

    def test_messages_refresh_offers_candidate_only_during_user_started_login(self):
        service, browser = self.connected_service()
        messages = ControlledMessageProvider(MessageInbox((Message(sender="DITO", body="123456 is your authentication code."),)))
        self.providers.append(messages)
        window = self.account_window(service=service, messages=messages)
        controls = window.sims_page.account_controls
        window.navigation.setCurrentRow(2)
        self.wait_until(lambda: not window.messages_controller.busy)
        self.assertFalse(service.state.otp_available)
        controls.connect_button.click()
        window.messages_page.refresh_button.click()
        self.wait_until(lambda: not window.messages_controller.busy)
        self.assertTrue(service.state.otp_available)
        self.assertEqual(len(messages.calls), 2)
        self.assertEqual(browser.opened, 1)

    def test_private_factory_error_uses_only_fixed_gui_text_and_no_output(self):
        def fail():
            raise RuntimeError("SYNTHETIC_PASSWORD_COOKIE_TOKEN")
        service = DitoAccountService(fail)
        window = self.account_window(service=service)
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            window.sims_page.account_controls.connect_button.click()
        self.assertEqual(output.getvalue() + error.getvalue(), "")
        self.assertNotIn("SYNTHETIC_PASSWORD_COOKIE_TOKEN", self.displayed_text(window))
        self.assertIn("could not be opened", window.sims_page.account_controls.detail_label.text())

    def test_window_shutdown_cancels_browser_and_revokes_callbacks(self):
        service, browser = self.connected_service()
        window = self.account_window(service=service)
        controls = window.sims_page.account_controls
        controls.connect_button.click()
        window.close()
        browser.callback(AuthEvent.AUTHENTICATED)
        self.assertTrue(browser.closed)
        self.assertEqual(service.state.phase, AccountPhase.DISCONNECTED)
        self.assertFalse(controls.connect_button.isEnabled())
        self.assertFalse(controls.disconnect_button.isEnabled())

    def test_live_and_demo_service_mismatches_are_rejected(self):
        with self.assertRaises(ValueError):
            MainWindow(self.provider(), demo=False, account_service=DemoAccountService())
        service, _browser = self.connected_service()
        with self.assertRaises(ValueError):
            MainWindow(self.provider(), demo=True, account_service=service)

    def test_demo_composition_connects_synthetically_without_browser_import(self):
        with patch("importlib.import_module", wraps=__import__("importlib").import_module) as imports:
            profiles, snapshot = active_dito_profiles(demo=True)
            window = app.create_window(demo=True, sim_profiles=profiles)
            self.windows.append(window)
            window.show()
            self.wait_until(lambda: window._startup_started and not window.refresh_controller.busy)
            window.render_snapshot(snapshot)
            window.navigation.setCurrentRow(1)
            controls = window.sims_page.account_controls
            controls.connect_button.click()
            self.assertEqual(controls.status_label.text(), "Connected")
            self.assertIn("DEMO", controls.detail_label.text())
            self.assertTrue(window.demo_label.isVisible())
            controls.disconnect_button.click()
            self.assertEqual(controls.status_label.text(), "Not connected")
            self.assertFalse(any("browser" in str(call) for call in imports.call_args_list))

    def test_injected_snapshot_provider_does_not_enable_account_browser(self):
        window = app.create_window(provider=self.provider())
        self.windows.append(window)
        self.assertFalse(window.sims_page.account_controls.connect_button.isEnabled())

    def test_malformed_injected_state_cannot_leak_private_fields_in_slot_errors(self):
        service, _browser = self.connected_service()
        window = self.account_window(service=service)
        controls = window.sims_page.account_controls
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            controls.render_state(AccountState(phase=["SYNTHETIC_PRIVATE_PHASE"]))
            controls.render_state(AccountState(issue=["SYNTHETIC_PRIVATE_COOKIE"]))
        self.assertEqual(output.getvalue() + error.getvalue(), "")
        self.assertEqual(controls.status_label.text(), "Connection unavailable")
        self.assertNotIn("SYNTHETIC_PRIVATE", self.displayed_text(controls))

    def test_expanded_inbox_exposes_message_beyond_old_three_record_window(self):
        entries = tuple(Message(sender="Example sender", body=f"Synthetic earlier message {index}")
                        for index in range(99)) + (
            Message(sender="DITO", body="123456 is your authentication code."),
        )
        messages = ControlledMessageProvider(MessageInbox(entries))
        messages.read_limit = 100
        self.providers.append(messages)
        window = self.account_window(messages=messages)
        window.navigation.setCurrentRow(2)
        self.wait_until(lambda: not window.messages_controller.busy)
        page = window.messages_page
        self.assertEqual(page.message_list.count(), 100)
        page.message_list.setCurrentRow(99)
        self.assertEqual(page.content_view.toPlainText(), entries[-1].body)

    def test_user_selection_resolves_ambiguous_otp_without_copy_or_submission(self):
        service, browser = self.connected_service()
        messages = ControlledMessageProvider(MessageInbox((
            Message(sender="DITO", body="123456 is your authentication code."),
            Message(sender="DITO", body="654321 is your authentication code."),
        )))
        self.providers.append(messages)
        window = self.account_window(service=service, messages=messages)
        window.sims_page.account_controls.connect_button.click()
        window.navigation.setCurrentRow(2)
        self.wait_until(lambda: not window.messages_controller.busy)
        self.assertFalse(service.state.otp_available)
        self.application.clipboard().setText("Synthetic user clipboard")
        window.messages_page.message_list.setCurrentRow(1)
        self.assertTrue(service.state.otp_available)
        self.assertEqual(service.otp_for_copy(), "654321")
        self.assertEqual(self.application.clipboard().text(), "Synthetic user clipboard")
        self.assertEqual(browser.opened, 1)
        self.assertEqual(service.state.phase, AccountPhase.CONNECTING)
