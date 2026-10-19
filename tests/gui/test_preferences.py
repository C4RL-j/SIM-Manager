"""Public preferences use isolated INI/fake stores, never user registry data."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea

from sim_manager.services.presentation import present_device
from sim_manager.models import DeviceState
from sim_manager.ui.pages.settings import SettingsPage
from sim_manager.ui.preferences import (
    AppPreferences, MemoryPreferencesStore, PREFERENCES_SAVE_FAILURE,
    QtPreferencesStore,
)
from sim_manager.ui.theme import STYLESHEET


PRIVATE_ERROR = "SYNTHETIC_PRIVATE_SETTINGS_ERROR"
KEYS = ("application/auto_refresh", "application/refresh_interval", "application/close_to_tray")


class FakeSettings:
    def __init__(self, values=None, *, failure=None, status=QSettings.Status.NoError):
        self.values = dict(values or {})
        self.failure = failure
        self.result_status = status
        self.reads = []
        self.writes = []

    def _fail(self, operation):
        if self.failure == operation:
            raise RuntimeError(PRIVATE_ERROR)

    def sync(self):
        self._fail("sync")

    def status(self):
        self._fail("status")
        return self.result_status

    def value(self, key):
        self._fail("value")
        self.reads.append(key)
        return self.values.get(key)

    def setValue(self, key, value):
        self._fail("setValue")
        self.writes.append((key, value))
        self.values[key] = value


class PreferencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        cls.application.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.no_network = patch("socket.socket", side_effect=AssertionError("Network forbidden"))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)
        self.widgets = []
        self.addCleanup(self.clear_widgets)

    def clear_widgets(self):
        for widget in self.widgets:
            widget.close()
            widget.deleteLater()
        self.application.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def page(self):
        page = SettingsPage()
        self.widgets.append(page)
        page.show()
        self.application.processEvents()
        return page

    def test_defaults_are_immutable_and_memory_store_never_uses_native_settings(self):
        defaults = AppPreferences()
        self.assertEqual((defaults.auto_refresh, defaults.refresh_interval, defaults.close_to_tray),
                         (True, 30, True))
        with self.assertRaises(FrozenInstanceError):
            defaults.auto_refresh = False
        for values in ({"auto_refresh": 1}, {"refresh_interval": True},
                       {"refresh_interval": 45}, {"close_to_tray": "true"}):
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, "Application preferences are invalid"):
                AppPreferences(**values)
        with patch("sim_manager.ui.preferences.QSettings", side_effect=AssertionError("Native settings forbidden")):
            store = MemoryPreferencesStore()
            self.assertEqual(store.load(), defaults)
            selected = AppPreferences(False, 60, True)
            self.assertTrue(store.save(selected))
            self.assertEqual(store.load(), selected)
            self.assertFalse(store.save({"private": PRIVATE_ERROR}))
            self.assertEqual(store.load(), selected)
            self.assertEqual(MemoryPreferencesStore(selected).load(), selected)

    def test_isolated_ini_round_trip_survives_a_fresh_store_and_writes_only_public_options(self):
        with tempfile.TemporaryDirectory(prefix="preferences-", dir=Path(__file__).parent) as directory:
            path = str(Path(directory) / "application.ini")
            first = QSettings(path, QSettings.Format.IniFormat)
            with patch("sim_manager.ui.preferences.QSettings", side_effect=AssertionError("Native settings forbidden")) as native:
                native.Format, native.Scope, native.Status = QSettings.Format, QSettings.Scope, QSettings.Status
                store = QtPreferencesStore(settings=first)
                self.assertEqual(store.load(), AppPreferences())
                selected = AppPreferences(False, 15, True)
                self.assertTrue(store.save(selected))
                native.assert_not_called()
            self.assertEqual(set(first.allKeys()), set(KEYS))
            second = QtPreferencesStore(settings=QSettings(path, QSettings.Format.IniFormat))
            self.assertEqual(second.load(), selected)
            self.assertTrue(second.save(AppPreferences(True, 60, False)))
            self.assertEqual(QtPreferencesStore(settings=QSettings(path, QSettings.Format.IniFormat)).load(),
                             AppPreferences(True, 60, False))

    def test_native_values_are_strict_and_invalid_fields_fall_back_individually(self):
        for values, expected in (
            ((False, 60, True), AppPreferences(False, 60, True)),
            (("false", "15", "true"), AppPreferences(False, 15, True)),
            (("yes", 45, "1"), AppPreferences()),
            ((0, True, 1), AppPreferences()),
            (([False], "030", {"private": PRIVATE_ERROR}), AppPreferences()),
            ((False, "60 seconds", True), AppPreferences(False, 30, True)),
        ):
            with self.subTest(values=values):
                settings = FakeSettings(dict(zip(KEYS, values)))
                self.assertEqual(QtPreferencesStore(settings=settings).load(), expected)
                self.assertEqual(settings.reads, list(KEYS))
        settings = FakeSettings({"unrelated/synthetic": "Keep this value"})
        store = QtPreferencesStore(settings=settings)
        self.assertFalse(store.save(PRIVATE_ERROR))
        self.assertEqual(settings.writes, [])
        self.assertTrue(store.save(AppPreferences()))
        self.assertEqual(tuple(key for key, _ in settings.writes), KEYS)
        self.assertEqual(settings.values["unrelated/synthetic"], "Keep this value")

    def test_settings_failures_return_closed_outcomes_without_private_output(self):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            for failure in ("sync", "status", "value", "setValue"):
                store = QtPreferencesStore(settings=FakeSettings(failure=failure))
                self.assertEqual(store.load(), AppPreferences())
                self.assertEqual(store.save(AppPreferences(False, 15, True)), failure == "value")
            store = QtPreferencesStore(settings=FakeSettings(status=QSettings.Status.AccessError))
            self.assertEqual(store.load(), AppPreferences())
            self.assertFalse(store.save(AppPreferences()))
            with patch("sim_manager.ui.preferences.QSettings", side_effect=RuntimeError(PRIVATE_ERROR)):
                unavailable = QtPreferencesStore()
            self.assertEqual(unavailable.load(), AppPreferences())
            self.assertFalse(unavailable.save(AppPreferences()))
        self.assertEqual(output.getvalue(), "")

    def test_settings_apply_preferences_without_emitting_edits(self):
        page = self.page()
        changes = []
        page.preferences_changed.connect(changes.append)
        self.assertTrue(page.auto_refresh_toggle.isChecked())
        self.assertEqual(page.refresh_interval_combo.currentData(), 30)
        self.assertTrue(page.close_to_tray_toggle.isChecked())
        self.assertEqual([page.refresh_interval_combo.itemData(index) for index in range(3)], [15, 30, 60])
        page.set_preferences(AppPreferences(False, 60, True))
        self.assertFalse(page.auto_refresh_toggle.isChecked())
        self.assertEqual(page.refresh_interval_combo.currentData(), 60)
        self.assertFalse(page.refresh_interval_combo.isEnabled())
        self.assertTrue(page.close_to_tray_toggle.isChecked())
        self.assertEqual(changes, [])
        page.render(present_device(DeviceState()))
        self.assertFalse(page.connection_details_toggle.isChecked())
        self.assertTrue(page.connection_details.isHidden())
        self.assertEqual(changes, [])

    def test_user_edits_emit_only_the_selected_public_preferences(self):
        page = self.page()
        page.set_tray_available(True)
        changes = []
        page.preferences_changed.connect(changes.append)
        QTest.mouseClick(page.auto_refresh_toggle, Qt.MouseButton.LeftButton,
                         pos=QPoint(8, page.auto_refresh_toggle.height() // 2))
        self.assertEqual(changes, [AppPreferences(False, 30, True)])
        self.assertFalse(page.refresh_interval_combo.isEnabled())
        QTest.mouseClick(page.auto_refresh_toggle, Qt.MouseButton.LeftButton,
                         pos=QPoint(8, page.auto_refresh_toggle.height() // 2))
        page.refresh_interval_combo.setCurrentIndex(page.refresh_interval_combo.findData(15))
        QTest.mouseClick(page.close_to_tray_toggle, Qt.MouseButton.LeftButton,
                         pos=QPoint(8, page.close_to_tray_toggle.height() // 2))
        self.assertEqual(changes[-1], AppPreferences(True, 15, False))
        self.assertEqual(len(changes), 4)

    def test_unavailable_tray_preserves_saved_choice_and_explains_effective_close_behavior(self):
        page = self.page()
        changes = []
        page.preferences_changed.connect(changes.append)
        page.set_preferences(AppPreferences(True, 30, True))
        page.set_tray_available(False)
        self.assertTrue(page.close_to_tray_toggle.isChecked())
        self.assertFalse(page.close_to_tray_toggle.isEnabled())
        self.assertIn("Closing the window will exit", page.tray_notice_label.text())
        QTest.mouseClick(page.close_to_tray_toggle, Qt.MouseButton.LeftButton,
                         pos=QPoint(8, page.close_to_tray_toggle.height() // 2))
        self.assertEqual(changes, [])
        QTest.mouseClick(page.auto_refresh_toggle, Qt.MouseButton.LeftButton,
                         pos=QPoint(8, page.auto_refresh_toggle.height() // 2))
        self.assertEqual(changes, [AppPreferences(False, 30, True)])
        page.set_tray_available(True)
        self.assertTrue(page.close_to_tray_toggle.isEnabled())
        self.assertTrue(page.close_to_tray_toggle.isChecked())
        self.assertTrue(page.tray_notice_label.isHidden())
        self.assertEqual(len(changes), 1)

    def test_notices_are_closed_plain_text_and_settings_fit_narrow_workspace(self):
        page = SettingsPage()
        scroller = QScrollArea()
        self.widgets.append(scroller)
        scroller.setWidgetResizable(True)
        scroller.setWidget(page)
        scroller.setStyleSheet(STYLESHEET)
        scroller.resize(500, 600)
        scroller.show()
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            page.set_preferences_notice(PRIVATE_ERROR)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(page.preferences_notice_label.text(), PREFERENCES_SAVE_FAILURE)
        self.assertEqual(page.preferences_notice_label.textFormat(), Qt.TextFormat.PlainText)
        self.assertNotIn(PRIVATE_ERROR, page.preferences_notice_label.text())
        self.application.processEvents()
        self.assertEqual(scroller.horizontalScrollBar().maximum(), 0)
        for widget in (page.auto_refresh_toggle, page.close_to_tray_toggle, page.refresh_interval_combo):
            self.assertLessEqual(widget.x() + widget.width(), widget.parentWidget().width())
        page.set_preferences_notice("")
        self.assertTrue(page.preferences_notice_label.isHidden())


if __name__ == "__main__":
    unittest.main()
