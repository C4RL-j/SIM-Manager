"""Windows startup UI uses an injected service; never the real Run registry."""

from contextlib import redirect_stderr, redirect_stdout
import io
from types import ModuleType
from unittest.mock import Mock, patch

from test_desktop import DesktopCase
from sim_manager import app
from sim_manager.ui.main_window import MainWindow
from sim_manager.ui.preferences import AppPreferences, MemoryPreferencesStore


class Startup:
    available = True
    issue = False

    def __init__(self, *, enabled=False, fail=False):
        self.enabled = enabled
        self.fail = fail
        self.writes = []
        self.reads = 0

    def is_enabled(self):
        self.reads += 1
        return self.enabled

    def set_enabled(self, enabled):
        self.writes.append(enabled)
        if self.fail:
            raise RuntimeError("SYNTHETIC_PRIVATE_STARTUP_ERROR")
        self.enabled = enabled
        return True


class StartupSettingsTests(DesktopCase):
    def startup_window(self, service):
        store = MemoryPreferencesStore(AppPreferences(auto_refresh=False))
        window = MainWindow(self.provider(), startup_service=service, preferences_store=store)
        self.windows.append(window)
        window.show()
        return window, store

    def test_startup_is_read_without_mutation_and_toggle_does_not_write_other_preferences(self):
        service = Startup()
        window, store = self.startup_window(service)
        page = window.settings_page
        original = store.load()
        changes = []
        page.preferences_changed.connect(changes.append)
        self.assertEqual(service.reads, 1)
        self.assertEqual(service.writes, [])
        self.assertFalse(page.start_with_windows_toggle.isChecked())
        self.assertTrue(page.start_with_windows_toggle.isEnabled())
        page.start_with_windows_toggle.click()
        self.assertEqual(service.writes, [True])
        self.assertTrue(page.start_with_windows_toggle.isChecked())
        page.start_with_windows_toggle.click()
        self.assertEqual(service.writes, [True, False])
        self.assertFalse(page.start_with_windows_toggle.isChecked())
        self.assertEqual(store.load(), original)
        self.assertEqual(changes, [])

    def test_existing_startup_choice_and_failure_are_safe(self):
        service = Startup(enabled=True, fail=True)
        window, _ = self.startup_window(service)
        self.assertTrue(window.settings_page.start_with_windows_toggle.isChecked())
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level="DEBUG"):
            window.settings_page.start_with_windows_toggle.click()
        self.assertEqual(output.getvalue(), "")
        self.assertTrue(window.settings_page.start_with_windows_toggle.isChecked())
        self.assertEqual(window.settings_page.startup_notice_label.text(),
                         "Windows startup could not be updated. Try again.")
        self.assertNotIn("SYNTHETIC_PRIVATE", self.displayed_text(window))

    def test_unavailable_startup_is_disabled_without_reading_registry(self):
        service = Startup()
        service.available = False
        window, _ = self.startup_window(service)
        self.assertFalse(window.settings_page.start_with_windows_toggle.isEnabled())
        self.assertEqual(service.reads, 0)
        self.assertEqual(service.writes, [])
        self.assertIn("Windows executable", window.settings_page.startup_notice_label.text())

    def test_normal_composition_uses_service_but_injected_providers_remain_isolated(self):
        service = Startup()
        with patch("sim_manager.services.windows_startup.WindowsStartupService", return_value=service) as factory:
            production = app.create_window(enable_tray=False)
            self.windows.append(production)
            factory.assert_called_once_with()
            factory.reset_mock()
            offline = app.create_window(provider=self.provider(), enable_tray=False)
            self.windows.append(offline)
            factory.assert_not_called()
        self.assertIs(production._windows_startup, service)
        self.assertIsNone(offline._windows_startup)
        self.assertEqual(service.writes, [])

    def test_release_diagnostic_dispatch_never_composes_normal_app_or_production_instance(self):
        module = ModuleType("sim_manager.ui.release_smoke")
        module.run_release_smoke = Mock(return_value=0)
        with patch.dict("sys.modules", {module.__name__: module}), \
                patch.object(app, "create_window") as compose, \
                patch.object(app, "create_application") as application:
            self.assertEqual(app.main(["--release-smoke", "synthetic-report.json"]), 0)
        module.run_release_smoke.assert_called_once_with("synthetic-report.json")
        compose.assert_not_called()
        application.assert_not_called()
