"""Normalized account presentation with synthetic values and no network I/O."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
import io

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from test_accounts import SyntheticBrowser
from test_desktop import DesktopCase, active_dito_profiles
from sim_manager.account_models import (
    AccountBucket, AccountData, AccountDataIssue, AccountDataResult, AccountPhase,
    AccountPromo, AccountState, AuthEvent, SessionValidity,
)
from sim_manager.models import DeviceState
from sim_manager.services.accounts import DitoAccountService
from sim_manager.services.sim_profiles import SimProfileService
from sim_manager.storage.sim_profiles import MemorySimProfileStore
from sim_manager.ui.main_window import MainWindow


class SyntheticDataAccount:
    is_demo = False

    def __init__(self):
        self.state = AccountState()
        self.listener = None
        self.calls = []

    def set_listener(self, listener):
        self.listener = listener
        if listener is not None:
            listener(self.state)

    def emit(self, state):
        self.state = state
        if self.listener is not None:
            self.listener(state)

    def connect(self):
        self.calls.append("connect")
        self.emit(AccountState(phase=AccountPhase.CONNECTING))
        return True

    def disconnect(self):
        self.calls.append("disconnect")
        self.emit(AccountState())

    def cancel(self):
        self.disconnect()

    def shutdown(self):
        self.calls.append("shutdown")

    def refresh_account(self):
        self.calls.append("refresh")
        self.emit(replace(self.state, data_refreshing=True))
        return True


class SyntheticAccountDataBrowser(SyntheticBrowser):
    def __init__(self):
        super().__init__()
        self.reads = []

    def refresh_account(self, callback):
        self.reads.append(callback)
        return True


def reported_data(**overrides):
    values = dict(
        updated_at=datetime(2026, 10, 9, 10, 11, 12, tzinfo=timezone.utc),
        load_balance="PHP 12.50", data_remaining="1.25 GB", expiry="2026-10-30",
        active_promos=(AccountPromo("<b>Synthetic plan</b>", "2026-10-29"),),
        sms_allowance="DITO: 5 SMS; Other networks: 3 SMS", call_allowance="8 minutes",
        data_buckets=(AccountBucket("Synthetic base", "1 GB", "2026-10-28"),
                      AccountBucket("Synthetic bonus", "256 MB", "2026-10-29")),
    )
    values.update(overrides)
    return AccountData(**values)


def connected(data=None, **values):
    return AccountState(phase=AccountPhase.CONNECTED, validity=SessionValidity.VALIDATED,
                        data=data, **values)


class AccountHomeTests(DesktopCase):
    def account_window(self, service=None):
        service = service if service is not None else SyntheticDataAccount()
        profiles, snapshot = active_dito_profiles()
        provider = self.provider(snapshot)
        window = MainWindow(provider, account_service=service, sim_profiles=profiles)
        self.windows.append(window)
        window.show()
        window.render_snapshot(snapshot)
        if isinstance(service, SyntheticDataAccount):
            service.calls.clear()
        return window, service, snapshot

    def test_verified_account_fields_precede_compact_connection_strip(self):
        window, service, _ = self.account_window()
        data = reported_data()
        service.emit(connected(data))
        home = window.home_page
        self.assertEqual(home.profile_values["load_balance"].text(), data.load_balance)
        self.assertEqual(home.profile_values["data_remaining"].text(), data.data_remaining)
        self.assertEqual(home.profile_values["sms_allowance"].text(), data.sms_allowance)
        self.assertEqual(home.profile_values["call_allowance"].text(), data.call_allowance)
        self.assertEqual(home.profile_values["load_expiry"].text(), "Oct 30, 2026")
        self.assertEqual(home.profile_values["promo_expiry"].text(), "Oct 29, 2026")
        self.assertIn("<b>Synthetic plan</b>", home.profile_values["promo"].text())
        self.assertIn("Synthetic base: 1 GB", home.buckets_value.text())
        self.assertIn("Synthetic bonus: 256 MB", home.buckets_value.text())
        self.assertIn("Oct 28, 2026", home.buckets_value.text())
        self.assertTrue(home.account_updated.text().startswith("Last updated: "))
        self.assertFalse(home.account_details.isHidden())
        self.assertEqual(home.layout().itemAt(0).widget(), home.profile_card)
        self.assertEqual(home.layout().itemAt(1).widget(), home.account_section)
        self.assertIs(home.account_card.parentWidget(), home.account_section)
        self.assertEqual(home.layout().itemAt(2).widget(), home.connection_strip)
        self.assertGreater(home.profile_values["data_remaining"].fontMetrics().height(),
                           home.profile_values["promo_expiry"].fontMetrics().height())
        self.assertGreater(home.profile_values["data_remaining"].fontMetrics().height(),
                           home.profile_values["load_balance"].fontMetrics().height())
        for label in (*home.profile_values.values(), home.buckets_value, home.account_updated):
            self.assertEqual(label.textFormat(), Qt.TextFormat.PlainText)

    def test_home_connecting_successful_data_and_visible_disconnect_restore_prompt(self):
        browser = SyntheticAccountDataBrowser()
        service = DitoAccountService(lambda: browser)
        window, _, _ = self.account_window(service)
        home = window.home_page
        self.assertEqual(window.navigation.currentRow(), 0)
        self.assertTrue(home.account_controls.connect_button.isVisible())
        self.assertTrue(home.account_card.isHidden())
        self.assertEqual(browser.opened, 0)
        home.account_controls.connect_button.click()
        self.assertEqual(service.state.phase, AccountPhase.CONNECTING)
        self.assertTrue(home.account_controls.isVisible())
        self.assertEqual(home.account_controls.connect_button.text(), "Show sign-in")
        self.assertEqual(home.account_controls.disconnect_button.text(), "Cancel")
        browser.callback(AuthEvent.AUTHENTICATED)
        self.assertEqual(len(browser.reads), 1)
        browser.reads[-1](AccountDataResult(data=reported_data()))
        self.assertTrue(home.account_controls.isHidden())
        self.assertTrue(home.account_card.isVisible())
        self.assertEqual(home.profile_values["load_balance"].text(), "PHP 12.50")
        self.assertTrue(home.account_disconnect_button.isVisible())
        home.account_disconnect_button.click()
        self.assertTrue(browser.closed)
        self.assertEqual(service.state.phase, AccountPhase.DISCONNECTED)
        self.assertIsNone(service.state.data)
        self.assertTrue(home.account_controls.connect_button.isVisible())
        self.assertTrue(home.account_card.isHidden())
        self.assertTrue(home.account_disconnect_button.isHidden())
        self.assertEqual(home.account_updated.text(), "")
        self.assertEqual(home.buckets_value.text(), "")

    def test_restart_keeps_saved_sim_metadata_but_never_restores_mydito_session_or_data(self):
        first_browser = SyntheticAccountDataBrowser()
        first_service = DitoAccountService(lambda: first_browser)
        saved_profiles, snapshot = active_dito_profiles()
        metadata_store = MemorySimProfileStore(saved_profiles.profiles)
        first_window = MainWindow(self.provider(snapshot), account_service=first_service,
                                 sim_profiles=SimProfileService(metadata_store))
        self.windows.append(first_window)
        first_window.show()
        first_window.render_snapshot(snapshot)
        first_window.home_page.account_controls.connect_button.click()
        first_browser.callback(AuthEvent.AUTHENTICATED)
        first_browser.reads[-1](AccountDataResult(data=reported_data()))
        profile_id = first_window.sim_profiles.active_profile.profile_id
        first_window.close()
        self.assertTrue(first_browser.closed)
        self.assertIsNone(first_service.state.data)

        next_browser = SyntheticAccountDataBrowser()
        next_service = DitoAccountService(lambda: next_browser)
        next_profiles = SimProfileService(metadata_store)
        next_window = MainWindow(self.provider(snapshot), account_service=next_service,
                                 sim_profiles=next_profiles)
        self.windows.append(next_window)
        next_window.show()
        self.assertTrue(next_window.start_initial_load())
        self.wait_until(lambda: not next_window.refresh_controller.busy)
        self.assertEqual(next_window.sim_profiles.active_profile.profile_id, profile_id)
        self.assertEqual(next_window.sim_profiles.active_profile.account_state.phase, AccountPhase.DISCONNECTED)
        self.assertIsNone(next_window.sim_profiles.active_profile.account_state.data)
        self.assertEqual(next_service.state.phase, AccountPhase.DISCONNECTED)
        self.assertEqual(next_browser.opened, 0)
        self.assertEqual(next_browser.reads, [])
        self.assertEqual(next_window.navigation.currentRow(), 0)
        self.assertTrue(next_window.home_page.account_controls.connect_button.isVisible())
        self.assertTrue(next_window.home_page.account_card.isHidden())
        self.assertEqual(next_window.home_page.account_updated.text(), "")
        self.assertEqual(next_window.home_page.profile_values["load_balance"].text(), "Not available")

    def test_unknown_totals_keep_reported_bucket_names_clearly_labelled(self):
        window, service, _ = self.account_window()
        service.emit(connected(reported_data(data_remaining=None, active_promos=(), expiry=None,
                                            sms_allowance=None, call_allowance=None)))
        home = window.home_page
        for key in ("data_remaining", "load_expiry", "sms_allowance", "call_allowance"):
            self.assertEqual(home.profile_values[key].text(), "Not available")
        self.assertEqual(home.profile_values["promo_expiry"].text(),
                         "Synthetic base: Oct 28, 2026\nSynthetic bonus: Oct 29, 2026")
        self.assertEqual(home.profile_values["promo"].text(), "Synthetic base\nSynthetic bonus")
        self.assertEqual(home.promo_caption.text(), "Reported buckets")
        self.assertTrue(home.allowance_row.isHidden())
        self.assertIn("256 MB", home.buckets_value.text())
        self.assertEqual(home.buckets_title.text(), "Balance / promo details")

    def test_manual_refresh_is_independent_and_failure_keeps_stale_values(self):
        browser = SyntheticAccountDataBrowser()
        service = DitoAccountService(lambda: browser)
        window, _, _ = self.account_window(service)
        window.home_page.account_controls.connect_button.click()
        browser.callback(AuthEvent.AUTHENTICATED)
        self.assertEqual(len(browser.reads), 1)
        first = reported_data()
        browser.reads[-1](AccountDataResult(data=first))
        home = window.home_page
        first_timestamp = home.account_updated.text()
        first_values = tuple(label.text() for label in home.profile_values.values())
        first_buckets = home.buckets_value.text()
        home.account_refresh_button.click()
        self.assertEqual(len(browser.reads), 2)
        self.assertFalse(window.refresh_controller.busy)
        self.assertFalse(home.account_refresh_button.isEnabled())
        self.assertEqual(home.account_refresh_button.text(), "Refreshing...")
        self.assertEqual(home.profile_values["load_balance"].text(), first.load_balance)
        self.assertEqual(tuple(label.text() for label in home.profile_values.values()), first_values)
        self.assertEqual(home.buckets_value.text(), first_buckets)
        self.assertEqual(home.account_updated.text(), first_timestamp)
        home.account_refresh_button.click()
        self.assertFalse(window.start_account_refresh())
        self.assertEqual(len(browser.reads), 2)
        latest = reported_data(
            updated_at=datetime(2026, 10, 18, 12, 30, tzinfo=timezone.utc),
            load_balance="PHP 23.75", data_remaining="3.5 GB", expiry="2026-11-30",
            active_promos=(AccountPromo("Synthetic refreshed plan", "2026-11-29"),),
            sms_allowance="7 SMS", call_allowance="11 minutes",
            data_buckets=(AccountBucket("Synthetic refreshed bucket", "3.5 GB", "2026-11-28"),),
        )
        browser.reads[-1](AccountDataResult(data=latest))
        for key, expected in (("load_balance", latest.load_balance), ("data_remaining", latest.data_remaining),
                              ("load_expiry", "Nov 30, 2026"), ("sms_allowance", latest.sms_allowance),
                              ("call_allowance", latest.call_allowance)):
            self.assertEqual(home.profile_values[key].text(), expected)
        self.assertEqual(home.profile_values["promo_expiry"].text(), "Nov 29, 2026")
        self.assertEqual(home.profile_values["promo"].text(), "Synthetic refreshed plan")
        self.assertEqual(home.buckets_value.text(), "Synthetic refreshed bucket: 3.5 GB · Expires Nov 28, 2026")
        self.assertNotEqual(home.account_updated.text(), first_timestamp)
        latest_timestamp = home.account_updated.text()
        latest_values = tuple(label.text() for label in home.profile_values.values())
        latest_buckets = home.buckets_value.text()
        home.account_refresh_button.click()
        self.assertEqual(len(browser.reads), 3)
        browser.reads[-1](AccountDataResult(issue=AccountDataIssue.UNAVAILABLE))
        self.assertTrue(home.account_refresh_button.isEnabled())
        self.assertEqual(home.account_notice.text(),
                         "Account refresh failed. Showing last successful values (stale). Try again.")
        self.assertEqual(tuple(label.text() for label in home.profile_values.values()), latest_values)
        self.assertEqual(home.buckets_value.text(), latest_buckets)
        self.assertEqual(home.account_updated.text(), latest_timestamp)
        home.account_refresh_button.click()
        recovered = replace(latest, updated_at=datetime(2026, 10, 18, 12, 31, tzinfo=timezone.utc))
        browser.reads[-1](AccountDataResult(data=recovered))
        self.assertEqual(len(browser.reads), 4)
        self.assertNotEqual(home.account_updated.text(), latest_timestamp)
        self.assertFalse(service.state.data_stale)
        self.assertNotIn("failed", home.account_notice.text())
        self.assertTrue(home.account_refresh_button.isEnabled())

    def test_initial_failed_refresh_shows_no_default_values_or_timestamp(self):
        browser = SyntheticAccountDataBrowser()
        service = DitoAccountService(lambda: browser)
        window, _, _ = self.account_window(service)
        window.home_page.account_controls.connect_button.click()
        browser.callback(AuthEvent.AUTHENTICATED)
        browser.reads[-1](AccountDataResult(issue=AccountDataIssue.UNSUPPORTED))
        home = window.home_page
        self.assertEqual(home.account_notice.text(), "Account refresh failed. Try again.")
        self.assertTrue(home.account_details.isHidden())
        self.assertTrue(home.account_refresh_button.isEnabled())
        self.assertEqual(home.account_updated.text(), "")
        self.assertEqual(home.buckets_value.text(), "")
        for key in ("load_balance", "data_remaining", "promo", "promo_expiry", "load_expiry", "sms_allowance", "call_allowance"):
            self.assertEqual(home.profile_values[key].text(), "Not available")

    def test_load_expiry_never_becomes_promo_expiry(self):
        window, service, _ = self.account_window()
        service.emit(connected(reported_data(active_promos=(), data_buckets=(), expiry="2026-12-31")))
        home = window.home_page
        self.assertEqual(home.profile_values["promo_expiry"].text(), "Not available")
        self.assertEqual(home.profile_values["load_expiry"].text(), "Dec 31, 2026")
        service.emit(connected(reported_data(active_promos=(), expiry="2026-12-31",
                                            data_buckets=(AccountBucket("Synthetic SMS", "50 SMS", "2026-11-30"),))))
        self.assertEqual(home.profile_values["promo_expiry"].text(), "Not available")

    def test_number_and_additional_details_are_explicit_and_progress_has_no_invented_total(self):
        window, service, snapshot = self.account_window()
        service.emit(connected(reported_data()))
        home = window.home_page
        self.assertTrue(home.profile_values["phone_number"].isHidden())
        self.assertFalse(home.phone_toggle.isChecked())
        home.phone_toggle.setFocus()
        QTest.keyClick(home.phone_toggle, Qt.Key.Key_Space)
        self.assertTrue(home.phone_toggle.isChecked())
        self.assertFalse(home.profile_values["phone_number"].isHidden())
        self.assertTrue(home.additional_details.isHidden())
        home.details_toggle.click()
        self.assertFalse(home.additional_details.isHidden())
        self.assertIn("Oct 30, 2026", home.profile_values["load_expiry"].text())
        self.assertEqual((home.data_progress.minimum(), home.data_progress.maximum()), (0, 100))
        self.assertEqual(home.data_progress.value(), -1)
        self.assertTrue(home.data_progress.isHidden())
        service.emit(connected(reported_data(), data_refreshing=True))
        self.assertTrue(home.phone_toggle.isChecked())
        self.assertTrue(home.data_progress.isHidden())
        window.render_snapshot(replace(snapshot, sim=replace(snapshot.sim, identity_key="iccid-v1:" + "b" * 64)))
        self.assertFalse(home.phone_toggle.isChecked())
        self.assertTrue(home.profile_values["phone_number"].isHidden())
        self.assertTrue(home.additional_details.isHidden())

    def test_reference_home_remains_responsive_with_reported_long_bucket_names(self):
        window, service, _ = self.account_window()
        service.emit(connected(reported_data(active_promos=(), sms_allowance=None, call_allowance=None,
                                            data_remaining="842.25 MB", data_buckets=(
            AccountBucket("General data", "842.25 MB", "2026-11-01 00:00:00"),
        ))))
        home = window.home_page
        window.resize(840, 600)
        self.application.processEvents()
        scroller = window.pages.widget(0)
        self.assertEqual(scroller.verticalScrollBar().maximum(), 0)
        self.assertEqual(scroller.horizontalScrollBar().maximum(), 0)
        self.assertGreaterEqual(home.connection_title.x(), home.connection_image.x() + home.connection_image.width() + 10)
        for label in (home.profile_values["data_remaining"], home.profile_values["promo_expiry"], home.connection_title):
            self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()))
        service.emit(connected(reported_data(active_promos=(), data_buckets=(
            AccountBucket("Synthetic " + "W" * 140, "2 GB", "2026-11-01"),
            AccountBucket("Synthetic bonus", "256 MB", "2026-11-02"),
        ))))
        for width, height in ((1120, 760), (840, 600)):
            window.resize(width, height)
            for expanded in (False, True):
                home.details_toggle.setChecked(expanded)
                self.application.processEvents()
                self.assertEqual(window.pages.widget(0).horizontalScrollBar().maximum(), 0)
                self.assertTrue(home.data_progress.isHidden())
                self.assertGreater(home.profile_values["data_remaining"].fontMetrics().height(),
                                   home.profile_values["promo_expiry"].fontMetrics().height())
    def test_expiry_clears_data_and_reuses_original_sign_in(self):
        window, service, snapshot = self.account_window()
        service.emit(connected(reported_data()))
        # Even an erroneous expired snapshot retaining data must not show it.
        service.emit(AccountState(phase=AccountPhase.EXPIRED, validity=SessionValidity.EXPIRED,
                                  data=reported_data(), data_issue=AccountDataIssue.EXPIRED))
        home = window.home_page
        self.assertTrue(home.account_details.isHidden())
        self.assertEqual(home.profile_values["load_balance"].text(), "Not available")
        self.assertEqual(home.buckets_value.text(), "")
        self.assertFalse(home.account_sign_in_button.isHidden())
        self.assertIn("Reconnect DITO", home.account_notice.text())
        window.render_snapshot(snapshot)
        self.assertEqual(home.account_controls.connect_button.text(), "Reconnect DITO")
        self.assertTrue(home.account_controls.detail_label.isVisible())
        self.assertIn("Session expired", home.account_controls.detail_label.text())
        home.account_sign_in_button.click()
        self.assertEqual(service.calls, ["connect"])
        self.assertEqual(service.state.phase, AccountPhase.CONNECTING)
        service.emit(AccountState(phase=AccountPhase.ERROR, data=reported_data(),
                                  data_issue=AccountDataIssue.ACCOUNT_MISMATCH))
        self.assertEqual(home.profile_values["load_balance"].text(), "Not available")
        self.assertIn("does not match the active SIM", home.account_notice.text())
        self.assertFalse(home.account_sign_in_button.isHidden())
        window.render_snapshot(snapshot)
        self.assertEqual(home.account_controls.connect_button.text(), "Sign in again")
        self.assertTrue(home.account_controls.detail_label.isVisible())
        self.assertIn("does not match the active SIM", home.account_controls.detail_label.text())

    def test_switch_account_or_sim_discards_old_data_and_late_callback(self):
        window, service, snapshot = self.account_window()
        previous = connected(reported_data())
        service.emit(previous)
        service.disconnect()
        self.assertEqual(window.home_page.profile_values["load_balance"].text(), "Not available")
        self.assertEqual(window.home_page.account_updated.text(), "")
        service.emit(previous)
        window.render_snapshot(replace(snapshot, sim=replace(snapshot.sim, identity_key="iccid-v1:" + "b" * 64)))
        self.assertEqual(window.home_page.profile_values["load_balance"].text(), "Not available")
        window.home_page.account_controls.state_changed.emit(previous)
        self.assertEqual(window.home_page.profile_values["load_balance"].text(), "Not available")
        self.assertIsNone(window.sim_profiles.active_profile)
        self.assertFalse(window.start_account_refresh())
        self.assertFalse(window.open_account_sign_in())

    def test_router_failure_preserves_account_and_refresh_errors_are_private(self):
        window, service, _ = self.account_window()
        service.emit(connected(reported_data()))
        window.render_snapshot(DeviceState())
        self.assertEqual(window.home_page.profile_values["load_balance"].text(), "PHP 12.50")
        def fail():
            raise RuntimeError("SYNTHETIC_PRIVATE_ACCOUNT_RESPONSE")
        service.refresh_account = fail
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            self.assertFalse(window.start_account_refresh())
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("SYNTHETIC_PRIVATE_ACCOUNT_RESPONSE", self.displayed_text(window))
        self.assertEqual(window.home_page.profile_values["load_balance"].text(), "PHP 12.50")
        window.close()
        self.assertEqual(window.home_page.profile_values["load_balance"].text(), "Not available")
        self.assertEqual(window.home_page.buckets_value.text(), "")
