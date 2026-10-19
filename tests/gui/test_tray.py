"""Synthetic native popup checks with a fake icon; no system tray or I/O."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
import io
import os
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtTest import QTest
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QLabel, QSystemTrayIcon, QWidget

from sim_manager.account_models import AccountData, AccountDataIssue, AccountPhase, AccountPromo, AccountState, SessionValidity
from sim_manager.models import ConnectionMode, ConnectionState, DeviceState, NetworkState, Readiness, SimState
from sim_manager.services.presentation import present_device
from sim_manager.sim_models import SimCarrier, SimProfile
from sim_manager.ui.tray import TrayDashboard, _popup_geometry


class FakeIcon(QObject):
    activated = Signal(object)

    def __init__(self, parent=None, *, available=True):
        super().__init__(parent)
        self.supported = available
        self.shows = self.hides = 0
        self.tooltip = ""
        self.context_menu = None

    def isSystemTrayAvailable(self):
        return self.supported

    def setIcon(self, icon):
        self.artwork = icon

    def setToolTip(self, value):
        self.tooltip = value

    def setContextMenu(self, menu):
        self.context_menu = menu

    def geometry(self):
        return QRect(740, 750, 24, 24)

    def show(self):
        self.shows += 1

    def hide(self):
        self.hides += 1


def profile():
    return SimProfile("00000000-0000-4000-8000-000000000001", "<b>Synthetic family SIM</b>",
                      "09920000001", SimCarrier.DITO, active=True)


def data(remaining="0 MB"):
    return AccountData(updated_at=datetime(2026, 10, 18, 12, tzinfo=timezone.utc),
                       data_remaining=remaining,
                       active_promos=(AccountPromo("Synthetic plan", "2026-11-01"),))


def connected(snapshot=None, **values):
    return AccountState(phase=AccountPhase.CONNECTED, validity=SessionValidity.VALIDATED,
                        data=snapshot, **values)


class TrayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        cls.application.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.owner = QWidget()
        self.owner.setGeometry(15, 15, 300, 200)
        self.owner.show()
        self.trays = []
        self.icons = []

    def tearDown(self):
        for tray in self.trays:
            tray.shutdown()
            tray.deleteLater()
        self.owner.close()
        self.owner.deleteLater()
        self.application.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def tray(self, *, available=True):
        def factory(parent):
            icon = FakeIcon(parent, available=available)
            self.icons.append(icon)
            return icon
        result = TrayDashboard(self.owner, icon_factory=factory)
        self.trays.append(result)
        return result

    def test_disabled_unavailable_and_failed_icons_never_hide_the_owner(self):
        with patch("sim_manager.ui.tray.QSystemTrayIcon", side_effect=AssertionError("Real tray forbidden")):
            disabled = TrayDashboard(self.owner, enabled=False)
        self.trays.append(disabled)
        self.assertFalse(disabled.available)
        self.assertIsNone(disabled.icon)
        self.assertFalse(disabled.toggle_popup())
        unavailable = self.tray(available=False)
        self.assertFalse(unavailable.available)
        self.assertEqual(self.icons[-1].shows, 0)
        with patch("sim_manager.ui.tray.application_icon", return_value=QIcon()):
            missing_artwork = self.tray()
        self.assertFalse(missing_artwork.available)
        self.assertEqual(self.icons[-1].shows, 0)
        output = io.StringIO()
        def fail(_parent):
            raise RuntimeError("SYNTHETIC_PRIVATE_ICON_FAILURE")
        with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level="DEBUG"):
            failed = TrayDashboard(self.owner, icon_factory=fail)
        self.trays.append(failed)
        self.assertFalse(failed.available)
        self.assertEqual(output.getvalue(), "")
        self.assertTrue(self.owner.isVisible())

    def test_verified_zero_stale_expiry_and_network_are_distinct_and_private(self):
        tray = self.tray()
        view = present_device(DeviceState(
            sim=SimState(present=True, readiness=Readiness.READY),
            network=NetworkState(connection_mode=ConnectionMode.LTE, connection=ConnectionState.CONNECTED),
        ))
        tray.render(profile(), connected(data()), view, auto_refresh=True, can_refresh=True,
                    schedule_status="Next refresh in 5 minutes")
        self.assertEqual(tray.popup.data_label.text(), "0 MB")
        self.assertEqual(tray.popup.name_label.text(), profile().name)
        self.assertIn("Nov 1, 2026", tray.popup.expiry_label.text())
        self.assertIn("Last updated:", tray.popup.updated_label.text())
        self.assertEqual(tray.popup.account_status_label.text(), "MyDITO connected")
        self.assertIn("LTE · Connected", tray.popup.network_status_label.text())
        self.assertNotIn(profile().phone_number, self.icons[0].tooltip)
        self.assertNotIn(profile().name, self.icons[0].tooltip)
        self.assertTrue(tray.popup.progress_bar.isHidden())
        self.assertEqual(tray.popup.progress_bar.value(), -1)
        for label in tray.popup.content.findChildren(QLabel):
            self.assertEqual(label.textFormat(), Qt.TextFormat.PlainText)
            self.assertNotIn(profile().phone_number, label.text())
        timestamp = tray.popup.updated_label.text()
        tray.render(profile(), connected(data(), data_stale=True), view,
                    auto_refresh=True, can_refresh=True)
        self.assertIn("stale", tray.popup.account_status_label.text())
        self.assertEqual(tray.popup.updated_label.text(), timestamp)
        tray.render(profile(), connected(data(), data_stale=True,
                                         data_issue=AccountDataIssue.RATE_LIMITED, retry_after_seconds=120),
                    view, auto_refresh=True, can_refresh=False, schedule_status="Retry in 2 minutes")
        self.assertIn("rate limited", tray.popup.account_status_label.text())
        self.assertEqual(tray.popup.updated_label.text(), timestamp)
        self.assertEqual(tray.popup.schedule_label.text(), "Retry in 2 minutes")
        self.assertFalse(tray.popup.refresh_button.isEnabled())
        tray.render(profile(), AccountState(phase=AccountPhase.EXPIRED, data=data()), view,
                    auto_refresh=True, can_refresh=False)
        self.assertEqual(tray.popup.account_status_label.text(), "Reconnect DITO")
        self.assertEqual(tray.popup.data_label.text(), "Unavailable")
        self.assertEqual(tray.popup.updated_label.text(), "")
        self.assertFalse(tray.popup.refresh_button.isEnabled())

    def test_popup_and_context_menu_actions_emit_only_shared_controller_intents(self):
        tray = self.tray()
        events = []
        tray.refresh_requested.connect(lambda: events.append("refresh"))
        tray.open_requested.connect(lambda: events.append("open"))
        tray.exit_requested.connect(lambda: events.append("exit"))
        tray.render(profile(), connected(data()), None, auto_refresh=False, can_refresh=True)
        self.assertTrue(tray.toggle_popup())
        tray.popup.refresh_button.click()
        tray.refresh_action.trigger()
        tray.popup.open_button.click()
        self.assertFalse(tray.popup.isVisible())
        tray.open_action.trigger()
        tray.popup.exit_button.click()
        tray.exit_action.trigger()
        self.assertEqual(events, ["refresh", "refresh", "open", "open", "exit", "exit"])
        self.assertEqual(len(self.icons), 1)
        self.assertEqual(self.icons[0].shows, 1)

    def test_left_toggle_escape_outside_click_and_deactivation_race(self):
        tray = self.tray()
        tray.icon.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
        self.application.processEvents()
        self.assertTrue(tray.popup.isVisible())
        QTest.keyClick(tray.popup, Qt.Key.Key_Escape)
        self.assertFalse(tray.popup.isVisible())
        tray.toggle_popup()
        self.application.processEvents()
        QTest.mouseClick(self.owner, Qt.MouseButton.LeftButton, pos=QPoint(15, 15))
        self.assertFalse(tray.popup.isVisible())
        tray.toggle_popup()
        QCoreApplication.sendEvent(tray.popup, QEvent(QEvent.Type.WindowDeactivate))
        self.application.processEvents()
        tray.icon.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
        self.assertFalse(tray.popup.isVisible())
        tray.icon.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
        self.application.processEvents()
        self.assertTrue(tray.popup.isVisible())
        self.assertTrue(self.owner.isVisible())

    def test_popup_placement_and_long_values_stay_inside_logical_work_area(self):
        for screen, anchor in (
            (QRect(0, 0, 1920, 1040), QRect(900, 1040, 24, 24)),
            (QRect(-1920, 0, 1920, 1040), QRect(-80, 1040, 24, 24)),
            (QRect(1920, -1080, 2560, 1440), QRect(1920, -1000, 24, 24)),
            (QRect(-1200, -900, 1200, 800), QRect()),
            (QRect(0, 0, 280, 220), QRect(250, 0, 24, 24)),
        ):
            with self.subTest(screen=screen):
                geometry = _popup_geometry(anchor, screen, QSize(324, 440))
                self.assertTrue(screen.contains(geometry))
                self.assertEqual(geometry.right(), screen.right())
        tray = self.tray()
        long_data = replace(data("W" * 160), active_promos=(AccountPromo("W" * 160, "2026-11-01"),))
        tray.render(profile(), connected(long_data), None, auto_refresh=False, can_refresh=True)
        tray.toggle_popup()
        self.application.processEvents()
        self.assertLessEqual(tray.popup.width(), 340)
        self.assertLessEqual(tray.popup.height(), 440)
        self.assertEqual(tray.popup.body.horizontalScrollBar().maximum(), 0)
        self.assertLessEqual(tray.popup.content.width(), tray.popup.body.viewport().width())
        # Native fonts can produce a size hint narrower than the fixed window.
        # Placement must align the displayed frame, not that preferred width.
        displayed_width = tray.popup.width()
        with patch.object(tray.popup, "sizeHint", return_value=QSize(120, tray.popup.height())):
            tray._place_popup()
            self.assertEqual(tray.popup.width(), displayed_width)
            self.assertEqual(tray.popup.frameGeometry().right(), tray.popup.screen().availableGeometry().right())
        tray.hide_popup()
        narrow = QRect(0, 0, 280, 600)
        class NarrowScreen:
            def availableGeometry(self):
                return narrow
        with patch.object(tray, "_screen", return_value=NarrowScreen()):
            tray.toggle_popup()
            self.application.processEvents()
            self.assertTrue(narrow.contains(tray.popup.geometry()),
                            (narrow, tray.popup.geometry(), tray.popup.minimumSize(), tray.popup.maximumSize()))
            self.assertEqual(tray.popup.geometry().right(), narrow.right())

    def test_shutdown_is_idempotent_and_clears_private_surfaces(self):
        tray = self.tray()
        tray.render(profile(), connected(data()), None, auto_refresh=True, can_refresh=True)
        tray.toggle_popup()
        icon = self.icons[0]
        tray.shutdown()
        tray.shutdown()
        self.assertFalse(tray.available)
        self.assertFalse(tray.popup.isVisible())
        self.assertEqual(icon.tooltip, "")
        self.assertIsNone(icon.context_menu)
        self.assertGreaterEqual(icon.hides, 1)
        self.assertTrue(all(label.text() == "" for label in tray.popup.content.findChildren(QLabel)))
        self.assertFalse(tray.toggle_popup())
