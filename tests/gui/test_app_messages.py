"""Offline composition checks for the native app's independent inbox path."""

from unittest.mock import patch

from PySide6.QtWidgets import QLabel

from test_desktop import DesktopCase
from test_messages import ControlledMessageProvider
from sim_manager import app


class AppMessagesTests(DesktopCase):
    def composed_window(self, **kwargs):
        window = app.create_window(**kwargs)
        self.windows.append(window)
        window.show()
        return window

    def test_production_startup_does_not_read_sms_before_messages_navigation(self):
        with patch("sim_manager.devices.d2.router.fetch_sms_response") as fetch:
            window = self.composed_window()
            self.wait_until(lambda: not window.refresh_controller.busy)
            self.assertIsNotNone(window.messages_controller)
            self.assertFalse(window.messages_page.loaded)
            self.assertIsNone(window.messages_page.last_refreshed_at)
            self.assertIsNone(window.messages_page.details_dialog)
            self.assertFalse(window.messages_controller.busy)
            self.assertTrue(any("Up to 20 messages" in label.text()
                                for label in window.messages_page.findChildren(QLabel)))
            fetch.assert_not_called()

    def test_demo_composition_loads_and_refreshes_only_synthetic_messages(self):
        with patch("sim_manager.devices.d2.router.fetch_sms_response") as fetch:
            window = self.composed_window(demo=True)
            window.navigation.setCurrentRow(2)
            page = window.messages_page
            # The first router observation can cancel the early inbox read and
            # queue its replacement. Idle alone also describes that brief gap.
            self.wait_until(lambda: page.loaded and not window.refresh_controller.busy
                            and not window.messages_controller.busy)
            self.assertEqual(page.message_list.count(), 2)
            self.assertIsNone(page.details_dialog)
            page.open_selected_message()
            self.assertIn("synthetic", page.details_dialog.content_view.toPlainText())
            page.details_dialog.close_button.click()
            self.wait_until(lambda: page.details_dialog is None)
            self.assertTrue(window.demo_label.isVisible())
            self.assertIn("DEMO", window.windowTitle())
            page.refresh_button.click()
            self.wait_until(lambda: not window.messages_controller.busy)
            self.assertEqual(page.message_list.count(), 2)
            fetch.assert_not_called()

    def test_injected_snapshot_provider_does_not_implicitly_enable_live_sms(self):
        window = self.composed_window(provider=self.provider())
        window.navigation.setCurrentRow(2)
        self.application.processEvents()
        self.assertIsNone(window.messages_controller)
        self.assertFalse(window.messages_page.refresh_button.isEnabled())
        self.assertEqual(window.messages_page.message_list.count(), 0)

    def test_explicit_message_provider_is_composed_and_cleared_on_close(self):
        provider = ControlledMessageProvider()
        self.providers.append(provider)
        window = self.composed_window(provider=self.provider(), message_provider=provider)
        window.navigation.setCurrentRow(2)
        self.wait_until(lambda: not window.messages_controller.busy)
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(window.messages_page.message_list.count(), 2)
        page = window.messages_page
        self.assertIsNone(page.details_dialog)
        page.open_selected_message()
        details = page.details_dialog
        self.assertTrue(details.content_view.toPlainText())
        cleared = []
        details.finished.connect(lambda _: cleared.append(details.content_view.toPlainText() == ""))
        window.close()
        self.assertEqual(window.messages_page.message_list.count(), 0)
        self.assertIsNone(page.details_dialog)
        self.assertEqual(cleared, [True])
        self.assertIsNone(page.last_refreshed_at)
        self.assertFalse(window.start_messages_refresh())
