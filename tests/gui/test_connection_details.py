"""Settings diagnostics reuse normalized snapshots, without device requests."""

from dataclasses import replace
import os
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea

from test_desktop import VALUE_KEYS, known_snapshot
from sim_manager.models import DeviceState
from sim_manager.services.presentation import present_device
from sim_manager.ui.pages.settings import SettingsPage
from sim_manager.ui.theme import STYLESHEET


class ConnectionDetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.network = patch("socket.socket", side_effect=AssertionError("Network forbidden"))
        self.network.start()
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.page = SettingsPage()
        self.scroll.setWidget(self.page)
        self.scroll.setStyleSheet(STYLESHEET)
        self.scroll.resize(560, 600)
        self.scroll.show()
        self.application.processEvents()

    def tearDown(self):
        self.scroll.close()
        self.scroll.deleteLater()
        self.application.processEvents()
        self.network.stop()

    def test_collapsed_by_default_with_unknowns_and_existing_settings(self):
        self.assertFalse(self.page.connection_details_toggle.isChecked())
        self.assertTrue(self.page.connection_details.isHidden())
        self.assertEqual(self.page.connection_details_toggle.accessibleName(), "Connection details")
        self.assertEqual(set(self.page.connection_values), VALUE_KEYS)
        self.assertEqual(self.page.connection_values["carrier"].accessibleName(), "Router carrier")
        self.assertEqual(self.page.connection_values["network_status"].text(), "Unknown")
        self.assertEqual(self.page.connection_values["rsrp"].text(), "—")
        self.assertEqual(self.page.router_address_label.text(), "192.168.1.1 (default)")
        self.assertTrue(self.page.forget_login_button.isHidden())
        self.assertEqual(self.scroll.horizontalScrollBar().maximum(), 0)

    def test_hidden_diagnostics_update_and_keyboard_disclosure_preserves_latest_values(self):
        first = present_device(known_snapshot())
        second = replace(first, rsrp="-88", secondary_rsrp="-90", bands="3 / 28", pin="PIN required")
        self.page.render(first)
        self.page.render(second)
        self.assertTrue(self.page.connection_details.isHidden())
        self.page.connection_details_toggle.setFocus()
        QTest.keyClick(self.page.connection_details_toggle, Qt.Key.Key_Space)
        self.application.processEvents()
        self.assertTrue(self.page.connection_details_toggle.isChecked())
        self.assertFalse(self.page.connection_details.isHidden())
        self.assertTrue(self.page.connection_details_toggle.text().startswith("▾"))
        self.assertEqual({key: label.text() for key, label in self.page.connection_values.items()},
                         {key: getattr(second, key) for key in VALUE_KEYS})
        self.assertEqual(self.page.connection_label.text(), second.router_status)
        QTest.mouseClick(self.page.connection_details_toggle, Qt.MouseButton.LeftButton)
        self.assertTrue(self.page.connection_details.isHidden())
        self.assertTrue(self.page.connection_details_toggle.text().startswith("▸"))
        self.page.render(present_device(DeviceState()))
        self.page.connection_details_toggle.click()
        self.assertEqual(self.page.connection_values["network_status"].text(), "Unknown")
        self.assertEqual(self.page.connection_values["rsrp"].text(), "—")

    def test_expanded_metrics_are_compact_plain_text_and_fit_narrow_settings(self):
        self.page.render(present_device(known_snapshot()))
        self.page.connection_details_toggle.click()
        for width in (560, 760, 560):
            with self.subTest(width=width):
                self.scroll.resize(width, 600)
                self.application.processEvents()
                self.assertEqual(self.scroll.horizontalScrollBar().maximum(), 0)
                for value in self.page.connection_values.values():
                    self.assertEqual(value.objectName(), "detail")
                    self.assertEqual(value.textFormat(), Qt.TextFormat.PlainText)
                    self.assertTrue(value.wordWrap())
                    self.assertTrue(value.accessibleName())
                    self.assertLessEqual(value.x() + value.width(), value.parentWidget().width())


if __name__ == "__main__":
    unittest.main()
