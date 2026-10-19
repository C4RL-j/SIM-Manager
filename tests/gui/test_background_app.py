"""Shared native app refresh/lifecycle with real services and a fake tray icon."""

from datetime import datetime, timezone
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from test_account_home import SyntheticAccountDataBrowser, reported_data
from test_desktop import DesktopCase, active_dito_profiles
from test_tray import FakeIcon
from sim_manager.account_models import AccountDataIssue, AccountDataResult, AccountPhase, AuthEvent
from sim_manager.services.accounts import DitoAccountService
from sim_manager.ui.main_window import MainWindow
from sim_manager.ui.preferences import AppPreferences, MemoryPreferencesStore
from sim_manager.ui.tray import TrayDashboard


class BackgroundAppTests(DesktopCase):
    def setUp(self):
        super().setUp()
        self.icons = []
        self.tray_available = True

        def create_icon(parent):
            icon = FakeIcon(parent, available=self.tray_available)
            self.icons.append(icon)
            return icon

        self.guards.enter_context(patch(
            "sim_manager.ui.main_window.TrayDashboard",
            side_effect=lambda parent, *, enabled: TrayDashboard(
                parent, enabled=enabled, icon_factory=create_icon,
            ),
        ))
        self.quit_application = self.guards.enter_context(patch.object(self.application, "quit"))

    def account_window(self, *, preferences=None, service=None, browser=None):
        profiles, snapshot = active_dito_profiles()
        browser = browser or SyntheticAccountDataBrowser()
        service = service or DitoAccountService(lambda: browser)
        store = MemoryPreferencesStore(preferences or AppPreferences())
        window = MainWindow(
            self.provider(snapshot), account_service=service, sim_profiles=profiles,
            preferences_store=store, enable_tray=True,
        )
        self.windows.append(window)
        window.show()
        window.render_snapshot(snapshot)
        return window, service, browser, store

    def sign_in(self, window, browser):
        window.home_page.account_controls.connect_button.click()
        self.assertEqual(browser.opened, 1)
        browser.callback(AuthEvent.AUTHENTICATED)
        self.application.processEvents()
        self.assertEqual(len(browser.reads), 1)

    def test_shared_home_and_tray_keep_verified_zero_and_stale_time_then_clear_on_expiry(self):
        window, service, browser, _ = self.account_window()
        self.sign_in(window, browser)
        first = reported_data(data_remaining="0 MB")
        browser.reads[0](AccountDataResult(data=first))
        self.application.processEvents()
        home, tray = window.home_page, window.tray_dashboard
        first_time = home.account_updated.text()
        self.assertEqual(home.profile_values["data_remaining"].text(), "0 MB")
        self.assertEqual(tray.popup.data_label.text(), "0 MB")
        self.assertEqual(tray.popup.updated_label.text(), first_time)
        self.assertTrue(window.account_refresh_controller._timer.isActive())

        # Both surfaces enter the same real service request slot.
        tray.refresh_action.trigger()
        self.assertEqual(len(browser.reads), 2)
        self.assertFalse(home.account_refresh_button.isEnabled())
        self.assertFalse(tray.refresh_action.isEnabled())
        home.account_refresh_button.click()
        self.assertFalse(window.start_account_refresh())
        self.assertEqual(len(browser.reads), 2)
        self.assertEqual(home.account_updated.text(), first_time)
        self.assertEqual(tray.popup.updated_label.text(), first_time)
        browser.reads[1](AccountDataResult(issue=AccountDataIssue.UNAVAILABLE))
        self.application.processEvents()
        self.assertIs(service.state.data, first)
        self.assertTrue(service.state.data_stale)
        self.assertIn("stale", home.account_notice.text())
        self.assertIn("stale", tray.popup.account_status_label.text())
        self.assertEqual(home.profile_values["data_remaining"].text(), "0 MB")
        self.assertEqual(tray.popup.data_label.text(), "0 MB")
        self.assertEqual(home.account_updated.text(), first_time)
        self.assertEqual(tray.popup.updated_label.text(), first_time)

        QTest.mouseClick(home.account_refresh_button, Qt.MouseButton.LeftButton)
        self.assertEqual(len(browser.reads), 3)
        browser.reads[2](AccountDataResult(issue=AccountDataIssue.EXPIRED))
        self.application.processEvents()
        self.assertIs(service.state.phase, AccountPhase.EXPIRED)
        self.assertIsNone(service.state.data)
        self.assertEqual(home.account_controls.connect_button.text(), "Reconnect DITO")
        self.assertTrue(home.account_controls.connect_button.isEnabled())
        self.assertEqual(tray.popup.account_status_label.text(), "Reconnect DITO")
        self.assertEqual(tray.popup.data_label.text(), "Unavailable")
        self.assertEqual(home.account_updated.text(), "")
        self.assertEqual(tray.popup.updated_label.text(), "")
        self.assertFalse(window.account_refresh_controller._timer.isActive())
        self.assertFalse(window.start_account_refresh())
        self.assertTrue(browser.closed)
        self.assertEqual(len(browser.reads), 3)

    def test_existing_runtime_session_gets_exactly_one_startup_read(self):
        browser = SyntheticAccountDataBrowser()
        service = DitoAccountService(lambda: browser)
        self.assertTrue(service.connect())
        browser.callback(AuthEvent.AUTHENTICATED)
        original = reported_data()
        browser.reads[0](AccountDataResult(data=original))
        window, _, _, _ = self.account_window(service=service, browser=browser)
        self.wait_until(lambda: len(browser.reads) == 2)
        self.application.processEvents()
        self.assertEqual(len(browser.reads), 2)
        self.assertIs(service.state.data, original)
        self.assertFalse(window.home_page.account_refresh_button.isEnabled())
        self.assertFalse(window.tray_dashboard.refresh_action.isEnabled())
        latest = reported_data(
            data_remaining="768 MB", updated_at=datetime(2026, 10, 18, 11, tzinfo=timezone.utc),
        )
        browser.reads[1](AccountDataResult(data=latest))
        self.application.processEvents()
        self.assertEqual(len(browser.reads), 2)
        self.assertEqual(window.home_page.profile_values["data_remaining"].text(), "768 MB")
        self.assertEqual(window.tray_dashboard.popup.data_label.text(), "768 MB")
        self.assertEqual(window.home_page.account_updated.text(), window.tray_dashboard.popup.updated_label.text())
        self.assertTrue(window.account_refresh_controller._timer.isActive())

    def test_existing_inflight_sign_in_read_is_not_duplicated_at_startup(self):
        browser = SyntheticAccountDataBrowser()
        service = DitoAccountService(lambda: browser)
        self.assertTrue(service.connect())
        browser.callback(AuthEvent.AUTHENTICATED)
        window, _, _, _ = self.account_window(service=service, browser=browser)
        self.application.processEvents()
        self.assertEqual(len(browser.reads), 1)
        self.assertTrue(service.state.data_refreshing)
        self.assertFalse(window.account_refresh_controller._timer.isActive())
        browser.reads[0](AccountDataResult(data=reported_data()))
        self.application.processEvents()
        self.assertEqual(len(browser.reads), 1)
        self.assertTrue(window.account_refresh_controller._timer.isActive())

    def test_turning_auto_refresh_off_keeps_manual_refresh_and_one_post_login_read(self):
        window, service, browser, store = self.account_window()
        self.sign_in(window, browser)
        browser.reads[0](AccountDataResult(data=reported_data()))
        self.application.processEvents()
        self.assertTrue(window.account_refresh_controller._timer.isActive())
        window.settings_page.auto_refresh_toggle.setChecked(False)
        self.assertFalse(store.load().auto_refresh)
        self.assertFalse(window.account_refresh_controller.enabled)
        self.assertFalse(window.account_refresh_controller._timer.isActive())
        self.assertTrue(window.home_page.account_refresh_button.isEnabled())
        self.assertTrue(window.tray_dashboard.refresh_action.isEnabled())
        window.tray_dashboard.refresh_action.trigger()
        self.assertEqual(len(browser.reads), 2)
        self.assertTrue(service.state.data_refreshing)
        browser.reads[1](AccountDataResult(data=reported_data(data_remaining="512 MB")))
        self.application.processEvents()
        self.assertEqual(window.home_page.profile_values["data_remaining"].text(), "512 MB")
        self.assertEqual(window.tray_dashboard.popup.data_label.text(), "512 MB")
        self.assertFalse(window.account_refresh_controller._timer.isActive())
        self.assertEqual(len(browser.reads), 2)

    def test_close_to_tray_retains_work_open_restores_and_explicit_exit_disposes(self):
        window, service, browser, _ = self.account_window(
            preferences=AppPreferences(close_to_tray=True),
        )
        self.sign_in(window, browser)
        window.close()
        self.application.processEvents()
        self.assertFalse(window.isVisible())
        self.assertFalse(window._closed)
        self.assertFalse(browser.closed)
        self.assertTrue(service.state.data_refreshing)
        self.assertTrue(window.tray_dashboard.available)
        self.quit_application.assert_not_called()
        browser.reads[0](AccountDataResult(data=reported_data(data_remaining="256 MB")))
        self.application.processEvents()
        self.assertEqual(window.tray_dashboard.popup.data_label.text(), "256 MB")
        self.assertTrue(window.account_refresh_controller._timer.isActive())
        window.tray_dashboard.open_action.trigger()
        self.assertTrue(window.isVisible())
        self.assertEqual(window.home_page.profile_values["data_remaining"].text(), "256 MB")
        icon = self.icons[0]
        window.tray_dashboard.exit_action.trigger()
        self.application.processEvents()
        self.assertTrue(window._closed)
        self.assertFalse(window.isVisible())
        self.assertTrue(browser.closed)
        self.assertFalse(window.account_refresh_controller._timer.isActive())
        self.assertFalse(window.tray_dashboard.available)
        self.assertEqual(icon.hides, 1)
        self.assertEqual(icon.tooltip, "")
        self.quit_application.assert_called_once_with()

    def test_absent_tray_uses_normal_close_even_when_preference_requests_background(self):
        self.tray_available = False
        window, service, browser, _ = self.account_window(
            preferences=AppPreferences(close_to_tray=True),
        )
        self.sign_in(window, browser)
        self.assertFalse(window.tray_dashboard.available)
        self.assertFalse(window.settings_page.close_to_tray_toggle.isEnabled())
        window.close()
        self.application.processEvents()
        self.assertTrue(window._closed)
        self.assertFalse(window.isVisible())
        self.assertTrue(browser.closed)
        self.assertFalse(window.account_refresh_controller._timer.isActive())
        self.assertEqual(self.icons[0].shows, 0)
        self.quit_application.assert_not_called()
        # A late result cannot restore Home, the tray or a disposed session.
        browser.reads[0](AccountDataResult(data=reported_data()))
        self.assertIsNone(service.state.data)
