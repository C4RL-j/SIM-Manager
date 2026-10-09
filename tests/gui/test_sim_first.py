"""Synthetic SIM ownership and desktop integration; no router or carrier I/O."""

from dataclasses import replace
from contextlib import redirect_stderr, redirect_stdout
import io

from test_accounts import SyntheticBrowser
from test_desktop import DesktopCase, known_snapshot
from test_messages import ControlledMessageProvider
from sim_manager.account_models import AccountPhase, AuthEvent
from sim_manager.message_models import Message, MessageInbox
from sim_manager.models import DeviceIssue, DeviceState, IssueCode, Readiness, SimState
from sim_manager.services.accounts import DitoAccountService
from sim_manager.services.sim_profiles import SimProfileService
from sim_manager.sim_models import SimCarrier
from sim_manager.storage.sim_profiles import MemorySimProfileStore
from sim_manager.ui.main_window import MainWindow


def sim_snapshot(key="a", phone="09170000001"):
    return replace(known_snapshot(), sim=SimState(
        readiness=Readiness.READY, identity_key="iccid-v1:" + key * 64,
        phone_number=phone,
    ))


class SimFirstIntegrationTests(DesktopCase):
    def sim_window(self, *, messages=None, account=None, profiles=None):
        window = MainWindow(self.provider(), message_provider=messages,
                            account_service=account, sim_profiles=profiles)
        self.windows.append(window)
        window.show()
        window.render_snapshot(sim_snapshot())
        return window

    def save_profile(self, window, name="Travel SIM", carrier=SimCarrier.DITO):
        window.navigation.setCurrentRow(1)
        page = window.sims_page
        page.create_name_input.setText(name)
        page.create_phone_input.setText("09170000001")
        page.create_carrier_combo.setCurrentIndex(page.create_carrier_combo.findData(carrier))
        page.create_button.click()
        self.assertIsNotNone(window.sim_profiles.active_profile)
        return window.sim_profiles.active_profile

    def test_unknown_offer_create_rename_and_home_quick_messages(self):
        messages = ControlledMessageProvider()
        self.providers.append(messages)
        window = self.sim_window(messages=messages)
        self.assertTrue(window.sim_profiles.can_create)
        self.assertFalse(window.sims_page.account_controls.connect_button.isEnabled())
        saved = self.save_profile(window)
        self.assertEqual(window.home_page.profile_values["name"].text(), saved.name)
        self.assertEqual(window.home_page.profile_values["phone_number"].text(), "09170000001")
        window.sims_page.rename_name_input.setText("Main SIM")
        window.sims_page.rename_button.click()
        self.assertEqual(window.sim_profiles.active_profile.profile_id, saved.profile_id)
        self.assertEqual(window.home_page.profile_values["name"].text(), "Main SIM")
        window.navigation.setCurrentRow(0)
        window.home_page.messages_button.click()
        self.wait_until(lambda: not window.messages_controller.busy)
        self.assertEqual(window.navigation.currentRow(), 2)
        self.assertIn("Main SIM", window.messages_page.sim_context_label.text())
        self.assertEqual(len(messages.calls), 1)

    def test_known_sim_switches_saved_profile_and_browsing_does_not_activate(self):
        window = self.sim_window()
        first = self.save_profile(window, "First SIM")
        window.render_snapshot(sim_snapshot("b"))
        self.assertIsNone(window.sim_profiles.active_profile)
        second = self.save_profile(window, "Second SIM")
        self.assertNotEqual(first.profile_id, second.profile_id)
        window.sims_page.profile_list.setCurrentRow(0)
        self.assertEqual(window.sim_profiles.active_profile.profile_id, second.profile_id)
        self.assertFalse(window.sims_page.account_controls.isVisible())
        window.render_snapshot(sim_snapshot())
        self.assertEqual(window.sim_profiles.active_profile.profile_id, first.profile_id)
        self.assertEqual(sum(profile.active for profile in window.sim_profiles.profiles), 1)
        self.assertIn("First SIM", window.messages_page.sim_context_label.text())
        self.assertTrue(window.sims_page.account_controls.isVisible())

    def test_switch_clears_account_otp_and_stale_inbox_delivery(self):
        browser = SyntheticBrowser()
        service = DitoAccountService(lambda: browser)
        messages = ControlledMessageProvider(
            MessageInbox((Message(sender="Example", body="Synthetic prior SIM body"),)),
            blocked=True, cooperative=False,
        )
        self.providers.append(messages)
        window = self.sim_window(messages=messages, account=service)
        self.save_profile(window)
        controls = window.sims_page.account_controls
        controls.connect_button.click()
        controls.offer_otp(MessageInbox((Message(sender="DITO", body="123456 is your authentication code."),)))
        controls.otp_copy_button.click()
        window.navigation.setCurrentRow(2)
        self.wait_until(messages.started.is_set)
        window.navigation.setCurrentRow(0)
        window.render_snapshot(sim_snapshot("b"))
        self.assertTrue(browser.closed)
        self.assertEqual(self.application.clipboard().text(), "")
        browser.callback(AuthEvent.AUTHENTICATED)
        self.assertEqual(service.state.phase, AccountPhase.DISCONNECTED)
        messages.release.set()
        self.wait_until(lambda: not window.messages_controller.busy)
        self.assertEqual(window.messages_page.message_list.count(), 0)
        self.assertEqual(window.messages_page.content_view.toPlainText(), "")
        self.assertFalse(window.messages_page.loaded)
        self.assertNotIn("prior SIM body", self.displayed_text(window))
        self.assertIsNone(window.sim_profiles.active_profile)

    def test_router_auth_failure_retains_same_sim_and_account_context(self):
        browser = SyntheticBrowser()
        service = DitoAccountService(lambda: browser)
        window = self.sim_window(account=service)
        saved = self.save_profile(window)
        window.sims_page.account_controls.connect_button.click()
        browser.callback(AuthEvent.AUTHENTICATED)
        window.render_snapshot(DeviceState(errors=(DeviceIssue("sim", IssueCode.AUTHENTICATION_REQUIRED),)))
        self.assertEqual(window.sim_profiles.active_profile.profile_id, saved.profile_id)
        self.assertEqual(window.sim_profiles.active_profile.account_state.phase, AccountPhase.CONNECTED)
        self.assertEqual(window.sims_page.account_controls.status_label.text(), "Connected")
        self.assertFalse(browser.closed)

    def test_saved_metadata_reloads_without_active_or_carrier_session(self):
        store = MemorySimProfileStore()
        profiles = SimProfileService(store=store)
        window = self.sim_window(profiles=profiles)
        saved = self.save_profile(window)
        reloaded = SimProfileService(store=store)
        self.assertIsNone(reloaded.active_profile)
        self.assertEqual(reloaded.profiles[0].profile_id, saved.profile_id)
        self.assertEqual(reloaded.profiles[0].account_state.phase, AccountPhase.DISCONNECTED)
        reloaded.observe(sim_snapshot())
        self.assertEqual(reloaded.active_profile.profile_id, saved.profile_id)
        self.assertEqual(reloaded.active_profile.account_state.phase, AccountPhase.DISCONNECTED)
        reloaded.close()

    def test_unverified_identity_does_not_match_a_saved_number(self):
        window = self.sim_window()
        saved = self.save_profile(window)
        unverified = replace(sim_snapshot(), sim=SimState(
            readiness=Readiness.READY, phone_number=saved.phone_number,
        ))
        window.render_snapshot(unverified)
        self.assertIsNone(window.sim_profiles.active_profile)
        self.assertTrue(window.sim_profiles.can_create)
        self.assertFalse(window.sims_page.account_controls.connect_button.isEnabled())
        self.assertEqual(window.home_page.profile_values["phone_number"].text(), saved.phone_number)

    def test_demo_and_live_profile_contexts_cannot_be_mixed(self):
        with self.assertRaises(ValueError):
            MainWindow(self.provider(), sim_profiles=SimProfileService(demo=True))
        with self.assertRaises(ValueError):
            MainWindow(self.provider(demo=True), demo=True, sim_profiles=SimProfileService())

    def test_disconnect_failure_cannot_claim_connected_for_another_sim(self):
        browser = SyntheticBrowser()
        class FailingDisconnect(DitoAccountService):
            fail_disconnect = False
            def disconnect(self):
                if self.fail_disconnect:
                    raise RuntimeError("SYNTHETIC_PRIVATE_SESSION_ERROR")
                return super().disconnect()
        service = FailingDisconnect(lambda: browser)
        window = self.sim_window(account=service)
        self.save_profile(window, "First SIM")
        window.render_snapshot(sim_snapshot("b"))
        second = self.save_profile(window, "Second SIM")
        window.render_snapshot(sim_snapshot())
        window.sims_page.account_controls.connect_button.click()
        browser.callback(AuthEvent.AUTHENTICATED)
        service.fail_disconnect = True
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            window.render_snapshot(sim_snapshot("b"))
        self.assertEqual(output.getvalue() + error.getvalue(), "")
        self.assertEqual(window.sim_profiles.active_profile.profile_id, second.profile_id)
        self.assertEqual(window.sim_profiles.active_profile.account_state.phase, AccountPhase.DISCONNECTED)
        self.assertEqual(window.sims_page.account_controls.status_label.text(), "Connection unavailable")
        self.assertFalse(window.sims_page.account_controls.connect_button.isEnabled())
        self.assertNotIn("SYNTHETIC_PRIVATE_SESSION_ERROR", self.displayed_text(window))
        service.fail_disconnect = False
