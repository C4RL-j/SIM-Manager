"""Offscreen native GUI tests with synthetic, cancellable snapshot providers.

This suite is deliberately separate from standard-library backend discovery.
No test authenticates to a router, opens a browser, or reads a live message.
"""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
import io
import os
import threading
import time
import unittest
from unittest.mock import patch


os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QCoreApplication, QEvent, QPoint, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit, QPushButton, QWidget

with patch("socket.socket", side_effect=AssertionError("Real sockets forbidden")):
    with patch("socket.create_connection", side_effect=AssertionError("Real connections forbidden")):
        from sim_manager import app
        from sim_manager.models import (
            Availability, CarrierEvidence, ConnectionMode, ConnectionState,
            DeviceIssue, DeviceState, IssueCode, NetworkState, RadioState,
            Readiness, SimState, WanState,
        )
        from sim_manager.services.device import RefreshCancelled
        from sim_manager.services.sim_profiles import SimProfileService
        from sim_manager.sim_models import SimCarrier
        from sim_manager.storage.sim_profiles import MemorySimProfileStore
        from sim_manager.ui.main_window import MainWindow


PRIVATE = "SYNTHETIC_PRIVATE_TOKEN"
SOURCES = ("wireless", "internet", "wan", "device", "wanStatus", "sim", "deviceDetails")
VALUE_KEYS = {
    "sim_state", "pin", "network_mode", "network_status", "carrier", "rsrp",
    "secondary_rsrp", "rsrq", "rssi", "sinr", "bands", "wan_state",
    "address", "router_status",
}


def known_snapshot(*, source="device:d2", errors=(), partial=False):
    """Safe observed labels/numbers; no concealed identifier is reconstructed."""
    return DeviceState(
        sim=SimState(readiness=Readiness.READY, pin_check_enabled=False),
        network=NetworkState(connection_mode=ConnectionMode.LTE, connection=ConnectionState.CONNECTED),
        radio=RadioState(bands=(1, 28), rsrp=-91, secondary_rsrp=-96, rsrq=-9, rssi=-82, sinr=22),
        wan=WanState(connection=ConnectionState.CONNECTED, address_availability=Availability.UNKNOWN),
        observed_at=datetime(2026, 10, 8, tzinfo=timezone.utc), source=source,
        successful_sources=SOURCES, errors=errors, partial=partial,
    )


def active_dito_profiles(*, demo=False):
    """A saved synthetic DITO identity with verified current SIM evidence."""
    profiles = SimProfileService(MemorySimProfileStore(), demo=demo)
    snapshot = known_snapshot(source="demo:d2" if demo else "device:d2")
    snapshot = replace(snapshot, sim=replace(
        snapshot.sim, present=True, identity_key="iccid-v1:" + "a" * 64,
        phone_number="+639000000001",
    ))
    profiles.observe(snapshot)
    profiles.create_profile("Synthetic DITO SIM", "+639000000001", SimCarrier.DITO)
    return profiles, snapshot


class ControlledProvider:
    """A bounded cooperative worker gate, with no real device or network work."""

    def __init__(self, snapshot=None, *, error=None, blocked=False, demo=False, cooperative=True):
        self.snapshot = DeviceState() if snapshot is None else snapshot
        self.error = error
        self.blocked = blocked
        self.is_demo = demo
        self.cooperative = cooperative
        self.calls = []
        self.started = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()

    def get_device_state(self, *, stop_event=None):
        self.calls.append((threading.get_ident(), stop_event))
        self.started.set()
        try:
            deadline = time.monotonic() + 2.0
            while self.blocked and not self.release.is_set():
                if self.cooperative and stop_event is not None and stop_event.is_set():
                    raise RefreshCancelled()
                if time.monotonic() >= deadline:
                    raise TimeoutError("Synthetic provider gate expired")
                self.release.wait(0.005)
            if self.error is not None:
                raise self.error
            return self.snapshot
        finally:
            self.finished.set()


class DesktopCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = app.create_application([])
        cls.application.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.guards = ExitStack()
        self.addCleanup(self.guards.close)
        for target in ("socket.socket", "socket.create_connection", "subprocess.Popen", "webbrowser.open"):
            self.guards.enter_context(patch(target, side_effect=AssertionError("External I/O forbidden")))
        # Normal composition must not read this PC's real saved credentials.
        self.guards.enter_context(patch("sim_manager.storage.windows_credentials.WindowsD2CredentialStore.load", return_value=None))
        for operation in ("save", "delete"):
            self.guards.enter_context(patch(
                "sim_manager.storage.windows_credentials.WindowsD2CredentialStore." + operation,
                side_effect=AssertionError("Real credential storage forbidden")))
        self.guards.enter_context(patch(
            "sim_manager.storage.sim_profiles.WindowsSimProfileStore.load", return_value=(),
        ))
        self.guards.enter_context(patch(
            "sim_manager.storage.sim_profiles.WindowsSimProfileStore.save",
            side_effect=AssertionError("Real SIM profile storage forbidden"),
        ))
        from sim_manager.ui.preferences import AppPreferences, MemoryPreferencesStore
        self.guards.enter_context(patch(
            "sim_manager.ui.preferences.QtPreferencesStore",
            side_effect=lambda: MemoryPreferencesStore(AppPreferences(auto_refresh=False)),
        ))
        self.windows = []
        self.providers = []
        self.addCleanup(self.clean_windows)

    def clean_windows(self):
        for provider in self.providers:
            provider.release.set()
        for window in self.windows:
            window.request_exit()
            window.refresh_controller.shutdown(timeout=1.0)
            window.deleteLater()
        self.application.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def provider(self, *args, **kwargs):
        provider = ControlledProvider(*args, **kwargs)
        self.providers.append(provider)
        return provider

    def window(self, provider=None, *, demo=False, factory=False):
        if provider is None and not factory:
            provider = self.provider()
        window = app.create_window(demo=demo, provider=provider) if factory else MainWindow(provider, demo=demo)
        self.windows.append(window)
        window.show()
        return window

    def wait_until(self, predicate, *, timeout=2.5):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail("GUI operation did not finish within its offline test deadline")
            self.application.processEvents()
            QTest.qWait(5)
        self.application.processEvents()

    def values(self, window):
        return {key: label.text() for key, label in window.settings_page.connection_values.items()}

    def displayed_text(self, window):
        text = [window.windowTitle()]
        for widget in (window, *window.findChildren(QWidget)):
            for name in ("text", "toPlainText", "toolTip", "statusTip", "whatsThis", "accessibleName", "accessibleDescription"):
                method = getattr(widget, name, None)
                if callable(method):
                    result = method()
                    if isinstance(result, str):
                        text.append(result)
        return "\n".join(text)


class ApplicationAndShellTests(DesktopCase):
    def test_application_factory_reuses_one_qapplication(self):
        # A stylesheet wraps the Fusion style in QStyleSheetStyle; its object
        # name is empty, so observe the requested base style at the factory.
        with patch.object(QApplication, "setStyle", wraps=QApplication.setStyle) as set_style:
            self.assertIs(app.create_application([]), self.application)
        set_style.assert_called_once_with("Fusion")
        self.assertIs(QApplication.instance(), self.application)
        self.assertTrue(self.application.styleSheet())

    def test_window_construction_has_five_pages_and_sensible_size(self):
        provider = self.provider()
        window = self.window(provider)
        self.assertEqual(window.windowTitle(), "SIM Manager")
        self.assertEqual(window.navigation.count(), 5)
        self.assertEqual([window.navigation.item(i).text() for i in range(5)], ["Home", "SIMs", "Messages", "History", "Settings"])
        self.assertEqual(window.pages.count(), 5)
        self.assertEqual(window.minimumWidth(), 840)
        self.assertEqual(window.minimumHeight(), 600)
        self.assertGreaterEqual(window.width(), 840)
        self.assertGreaterEqual(window.height(), 600)
        self.assertEqual(provider.calls, [])
        self.assertFalse(window.refresh_controller.busy)

    def test_navigation_switches_existing_pages(self):
        window = self.window()
        for index, page in enumerate((window.home_page, window.sims_page, window.messages_page, window.history_page, window.settings_page)):
            window.navigation.setCurrentRow(index)
            self.application.processEvents()
            self.assertIs(window.pages.currentWidget().widget(), page)

    def test_window_resizes_without_losing_navigation_or_values(self):
        window = self.window()
        window.render_snapshot(known_snapshot())
        before = self.values(window)
        for width, height in ((840, 600), (1300, 850)):
            window.resize(width, height)
            self.application.processEvents()
            self.assertGreater(window.pages.width(), 0)
            self.assertGreater(window.navigation.width(), 0)
            self.assertEqual(self.values(window), before)

    def test_messages_shell_has_no_send_or_delete_actions(self):
        window = self.window()
        buttons = [button.text().lower() for button in window.messages_page.findChildren(QPushButton)]
        self.assertFalse(any("send" in text or "delete" in text for text in buttons))
        self.assertTrue(window.messages_page.findChildren(QLabel))

    def test_settings_fields_are_read_only_and_do_not_request_credentials(self):
        window = self.window()
        for field in window.settings_page.findChildren(QLineEdit):
            self.assertTrue(field.isReadOnly())
        text = self.displayed_text(window.settings_page)
        self.assertIn("192.168.1.1", text)
        for sensitive in ("password", "authorization", "cookie", "token"):
            self.assertNotIn(sensitive, text.lower())

    def test_factory_schedules_first_refresh_through_injected_provider(self):
        provider = self.provider(known_snapshot())
        window = self.window(provider, factory=True)
        self.wait_until(lambda: len(provider.calls) == 1 and not window.refresh_controller.busy)
        self.assertEqual(self.values(window)["sim_state"], "Ready")

    def test_live_factory_without_session_launches_authentication_required(self):
        window = self.window(factory=True)
        self.wait_until(lambda: window.status_label.text() == "Authentication required")
        self.assertEqual(self.values(window)["carrier"], "Unknown")
        self.assertTrue(window.demo_label.isHidden())

    def test_explicit_demo_factory_has_persistent_badge_and_safe_data(self):
        window = self.window(demo=True, factory=True)
        self.wait_until(lambda: self.values(window)["sim_state"] == "Ready")
        self.assertFalse(window.demo_label.isHidden())
        self.assertIn("DEMO", window.demo_label.text())
        self.assertEqual(self.values(window)["carrier"], "Unknown")
        window.navigation.setCurrentRow(4)
        self.application.processEvents()
        self.assertFalse(window.demo_label.isHidden())

    def test_demo_provider_requires_explicit_demo_mode_before_starting_work(self):
        provider = self.provider(demo=True)
        with self.assertRaises(ValueError) as caught:
            MainWindow(provider, demo=False)
        self.assertNotIn(PRIVATE, str(caught.exception))
        self.assertEqual(provider.calls, [])


class OverviewRenderingTests(DesktopCase):
    def test_known_normalized_snapshot_renders_verified_values_without_units(self):
        window = self.window()
        window.render_snapshot(known_snapshot())
        self.assertEqual(self.values(window), {
            "sim_state": "Ready", "pin": "Off", "network_mode": "LTE",
            "network_status": "Connected", "carrier": "Unknown", "rsrp": "-91",
            "secondary_rsrp": "-96", "rsrq": "-9", "rssi": "-82", "sinr": "22",
            "bands": "1 / 28", "wan_state": "Connected", "address": "Unknown",
            "router_status": "Status available",
        })
        self.assertEqual(window.status_label.text(), "● Router data available")
        self.assertNotIn("dBm", self.displayed_text(window))

    def test_unknown_snapshot_uses_unknown_or_dash_without_fabricating_values(self):
        window = self.window()
        window.render_snapshot(DeviceState())
        values = self.values(window)
        self.assertEqual(set(values), VALUE_KEYS)
        for key in ("sim_state", "pin", "network_mode", "network_status", "carrier", "wan_state", "address"):
            self.assertEqual(values[key], "Unknown")
        for key in ("rsrp", "secondary_rsrp", "rsrq", "rssi", "sinr", "bands"):
            self.assertEqual(values[key], "—")

    def test_partial_snapshot_keeps_known_values_and_clear_notice(self):
        window = self.window()
        snapshot = known_snapshot(errors=(DeviceIssue("wireless", IssueCode.UNAVAILABLE),), partial=True)
        window.render_snapshot(snapshot)
        self.assertEqual(self.values(window)["rsrp"], "-91")
        self.assertEqual(self.values(window)["router_status"], "Partial data")
        self.assertEqual(window.status_label.text(), "Router status unavailable")

    def test_incomplete_snapshot_without_specific_error_has_partial_data_notice(self):
        window = self.window()
        window.render_snapshot(known_snapshot(partial=True))
        self.assertEqual(self.values(window)["rsrp"], "-91")
        self.assertEqual(self.values(window)["router_status"], "Partial data")
        self.assertEqual(window.status_label.text(), "Partial device data")

    def test_authentication_required_is_friendly_and_does_not_display_identifiers(self):
        window = self.window()
        snapshot = DeviceState(errors=tuple(DeviceIssue(source, IssueCode.AUTHENTICATION_REQUIRED) for source in SOURCES))
        window.render_snapshot(snapshot)
        self.assertEqual(window.status_label.text(), "Authentication required")
        self.assertEqual(self.values(window)["router_status"], "Authentication required")
        self.assertEqual(self.values(window)["rsrp"], "—")

    def test_closed_error_codes_have_clear_safe_status_messages(self):
        window = self.window()
        expected = {
            IssueCode.UNAVAILABLE: "Router status unavailable",
            IssueCode.MALFORMED_RESPONSE: "Malformed response",
            IssueCode.TIMEOUT: "Router status unavailable",
            IssueCode.CANCELLED: "Refresh cancelled",
        }
        for code, message in expected.items():
            with self.subTest(code=code):
                window.render_snapshot(DeviceState(errors=(DeviceIssue("wireless", code),)))
                self.assertEqual(window.status_label.text(), message)

    def test_private_or_wrong_typed_model_values_never_reach_visible_text(self):
        window = self.window()
        state = DeviceState(
            sim=SimState(readiness=PRIVATE, pin_check_enabled=PRIVATE, imsi_availability=PRIVATE),
            network=NetworkState(operator=PRIVATE, connection=PRIVATE, connection_mode=PRIVATE),
            radio=RadioState(rsrp=PRIVATE, secondary_rsrp=PRIVATE, rsrq=PRIVATE, rssi=PRIVATE, sinr=PRIVATE, bands=(PRIVATE,)),
            wan=WanState(apn=PRIVATE, pdp_type=PRIVATE, ip_family=PRIVATE, connection=PRIVATE, address_availability=PRIVATE),
            carrier_evidence=CarrierEvidence(operator=PRIVATE, plmn=PRIVATE, mcc=PRIVATE, mnc=PRIVATE),
            source=PRIVATE, observed_at=PRIVATE, successful_sources=(PRIVATE,), errors=(DeviceIssue(PRIVATE, PRIVATE),),
        )
        window.render_snapshot(state)
        self.assertNotIn(PRIVATE, self.displayed_text(window))
        self.assertEqual(self.values(window)["carrier"], "Unknown")

    def test_demo_snapshot_cannot_be_rendered_as_live_data(self):
        window = self.window()
        window.render_snapshot(known_snapshot(source="demo:d2"))
        self.assertNotEqual(self.values(window)["rsrp"], "-91")
        self.assertEqual(self.values(window)["carrier"], "Unknown")
        self.assertIn("unavailable", window.status_label.text().lower())


class PolishedShellTests(DesktopCase):
    def test_navigation_icons_keep_accessible_page_names(self):
        window = self.window()
        self.assertEqual(window.navigation.accessibleName(), "Pages")
        for index, name in enumerate(("Home", "SIMs", "Messages", "History", "Settings")):
            item = window.navigation.item(index)
            self.assertEqual(item.text(), name)
            self.assertFalse(item.icon().isNull())
            window.navigation.setCurrentRow(index)
            self.assertTrue(item.isSelected())
            self.assertEqual(window.title_label.text(), name)

    def test_refresh_action_is_visible_only_on_home(self):
        provider = self.provider()
        window = self.window(provider)
        for index in (0, 1, 2, 3, 4, 0):
            window.navigation.setCurrentRow(index)
            self.application.processEvents()
            self.assertEqual(window.refresh_button.isVisible(), index == 0)
            self.assertFalse(window.cancel_button.isVisible())
        self.assertEqual(provider.calls, [])

    def test_cancel_remains_accessible_when_navigating_during_refresh(self):
        provider = self.provider(known_snapshot(), blocked=True)
        window = self.window(provider)
        window.start_refresh()
        self.wait_until(provider.started.is_set)
        for index in (0, 1, 2, 3, 4):
            window.navigation.setCurrentRow(index)
            self.application.processEvents()
            self.assertEqual(window.refresh_button.isVisible(), index == 0)
            self.assertFalse(window.refresh_button.isEnabled())
            self.assertTrue(window.cancel_button.isVisible())
            self.assertTrue(window.cancel_button.isEnabled())
        QTest.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertEqual(window.status_label.text(), "Refresh cancelled")
        self.assertFalse(window.refresh_button.isVisible())
        self.assertFalse(window.cancel_button.isVisible())
        window.navigation.setCurrentRow(0)
        self.assertTrue(window.refresh_button.isVisible())
        self.assertTrue(window.refresh_button.isEnabled())

    def test_success_status_is_compact_and_warning_error_states_remain_banners(self):
        window = self.window()
        window.render_snapshot(known_snapshot())
        self.application.processEvents()
        self.assertEqual(window.status_label.text(), "● Router data available")
        self.assertIs(window.status_label.property("banner"), False)
        self.assertEqual(window.status_label.textFormat(), Qt.TextFormat.PlainText)
        compact_height = window.status_surface.height()
        for code in (IssueCode.AUTHENTICATION_REQUIRED, IssueCode.MALFORMED_RESPONSE):
            window.render_snapshot(DeviceState(errors=(DeviceIssue("wireless", code),)))
            self.application.processEvents()
            self.assertIs(window.status_label.property("banner"), True)
            self.assertGreater(window.status_surface.height(), compact_height)
        window.render_snapshot(known_snapshot())
        self.application.processEvents()
        self.assertIs(window.status_label.property("banner"), False)
        self.assertLessEqual(window.status_surface.height(), compact_height)

    def test_demo_disclaimer_survives_navigation_busy_and_error_states(self):
        provider = self.provider(known_snapshot(source="demo:d2"), blocked=True, demo=True)
        window = self.window(provider, demo=True)
        window.render_snapshot(known_snapshot(source="demo:d2"))
        self.assertEqual(window.status_label.text(), "● Demo data • Router not connected")
        self.assertIs(window.status_label.property("banner"), False)
        for index in range(5):
            window.navigation.setCurrentRow(index)
            self.application.processEvents()
            self.assertTrue(window.demo_label.isVisible())
            self.assertTrue(window.demo_note.isVisible())
            self.assertEqual(window.demo_note.text(), "Offline fixture data\nRouter not connected")
        window.start_refresh()
        self.wait_until(provider.started.is_set)
        self.assertEqual(window.status_label.text(), "Refreshing…")
        self.assertTrue(window.demo_label.isVisible())
        self.assertTrue(window.demo_note.isVisible())
        provider.error = RuntimeError(PRIVATE)
        provider.release.set()
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertEqual(window.status_label.text(), "Unknown error")
        self.assertTrue(window.demo_label.isVisible())
        self.assertTrue(window.demo_note.isVisible())
        self.assertNotIn(PRIVATE, self.displayed_text(window))

    def test_diagnostics_move_to_collapsed_settings_and_stay_available(self):
        window = self.window()
        window.render_snapshot(known_snapshot())
        self.application.processEvents()
        self.assertFalse(window.settings_page.connection_details_toggle.isChecked())
        self.assertTrue(window.settings_page.connection_details.isHidden())
        self.assertEqual(set(window.home_page.values), {"network_status", "network_mode", "sim_state"})
        self.assertNotIn("Signal", [label.text() for label in window.home_page.findChildren(QLabel)])
        self.assertNotIn("Router carrier", [label.text() for label in window.home_page.findChildren(QLabel)])
        calls = list(window.refresh_controller._provider.calls)
        window.navigation.setCurrentRow(4)
        window.settings_page.connection_details_toggle.click()
        self.application.processEvents()
        self.assertFalse(window.settings_page.connection_details.isHidden())
        self.assertEqual(window.refresh_controller._provider.calls, calls)
        labels = window.settings_page.connection_values
        identity = labels["carrier"]
        self.assertEqual(identity.text(), "Unknown")
        self.assertIs(identity.parentWidget(), labels["network_mode"].parentWidget())
        self.assertIs(identity.parentWidget(), labels["sim_state"].parentWidget())
        self.assertLess(identity.mapTo(window.settings_page, QPoint()).y(), labels["rsrp"].mapTo(window.settings_page, QPoint()).y())
        for label in labels.values():
            self.assertEqual(label.textFormat(), Qt.TextFormat.PlainText)
            self.assertTrue(label.accessibleName())

    def test_default_home_fits_and_minimum_size_avoids_horizontal_scrolling(self):
        window = self.window()
        window.render_snapshot(known_snapshot())
        window.resize(1120, 760)
        self.application.processEvents()
        home = window.pages.widget(0)
        self.assertEqual(home.verticalScrollBar().maximum(), 0)
        self.assertEqual(home.horizontalScrollBar().maximum(), 0)
        window.resize(840, 600)
        for index in range(5):
            window.navigation.setCurrentRow(index)
            self.application.processEvents()
            self.assertEqual(window.pages.currentWidget().horizontalScrollBar().maximum(), 0)
        self.assertEqual(set(self.values(window)), VALUE_KEYS)

    def test_settings_groups_keep_router_and_application_information_read_only(self):
        window = self.window()
        text = self.displayed_text(window.settings_page)
        self.assertIn("Router information", text)
        self.assertIn("Application information", text)
        self.assertIn("Router settings are read-only", text)
        self.assertEqual(set(window.settings_page.findChildren(QPushButton)), {
            window.settings_page.forget_login_button,
            window.settings_page.connection_details_toggle,
        })


class RefreshLifecycleTests(DesktopCase):
    def test_refresh_runs_off_main_thread_and_keeps_event_loop_responsive(self):
        provider = self.provider(known_snapshot(), blocked=True)
        window = self.window(provider)
        delivered_on = []
        window.refresh_controller.snapshot_ready.connect(lambda state: delivered_on.append(threading.get_ident()))
        self.assertTrue(window.start_refresh())
        self.wait_until(provider.started.is_set)
        callbacks = []
        QTimer.singleShot(0, lambda: callbacks.append(threading.get_ident()))
        self.wait_until(lambda: bool(callbacks))
        self.assertNotEqual(provider.calls[0][0], threading.get_ident())
        self.assertEqual(callbacks, [threading.get_ident()])
        self.assertTrue(window.refresh_controller.busy)
        self.assertFalse(window.refresh_button.isEnabled())
        self.assertTrue(window.cancel_button.isEnabled())
        self.assertEqual(window.status_label.text(), "Refreshing…")
        provider.release.set()
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertEqual(delivered_on, [threading.get_ident()])
        self.assertEqual(self.values(window)["rsrp"], "-91")
        self.assertTrue(window.refresh_button.isEnabled())
        self.assertFalse(window.cancel_button.isEnabled())

    def test_duplicate_refresh_is_rejected_until_current_request_finishes(self):
        provider = self.provider(known_snapshot(), blocked=True)
        window = self.window(provider)
        self.assertTrue(window.start_refresh())
        self.wait_until(provider.started.is_set)
        self.assertFalse(window.start_refresh())
        self.assertFalse(window.refresh_controller.start())
        self.assertEqual(len(provider.calls), 1)
        provider.release.set()
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertTrue(window.start_refresh())
        self.wait_until(lambda: len(provider.calls) == 2 and not window.refresh_controller.busy)

    def test_cancel_passes_event_and_restores_idle_buttons_with_friendly_state(self):
        provider = self.provider(known_snapshot(), blocked=True)
        window = self.window(provider)
        window.start_refresh()
        self.wait_until(provider.started.is_set)
        stop = provider.calls[0][1]
        self.assertIsInstance(stop, threading.Event)
        QTest.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertTrue(stop.is_set())
        self.assertEqual(window.status_label.text(), "Refresh cancelled")
        self.assertEqual(self.values(window)["rsrp"], "—")
        self.assertTrue(window.refresh_button.isEnabled())

    def test_worker_errors_are_generic_and_clear_stale_fields(self):
        provider = self.provider(error=RuntimeError(PRIVATE))
        window = self.window(provider)
        window.render_snapshot(known_snapshot())
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            window.start_refresh()
            self.wait_until(lambda: provider.finished.is_set() and not window.refresh_controller.busy)
        self.assertNotIn(PRIVATE, output.getvalue() + self.displayed_text(window))
        self.assertEqual(self.values(window)["rsrp"], "—")
        self.assertEqual(self.values(window)["carrier"], "Unknown")
        self.assertTrue(window.status_label.text())

    def test_worker_baseexception_does_not_reach_thread_exception_hook(self):
        provider = self.provider(error=SystemExit(PRIVATE))
        window = self.window(provider)
        with patch("threading.excepthook") as hook:
            window.start_refresh()
            self.wait_until(lambda: provider.finished.is_set() and not window.refresh_controller.busy)
        hook.assert_not_called()
        self.assertNotIn(PRIVATE, self.displayed_text(window))

    def test_worker_exception_classes_map_to_fixed_friendly_messages(self):
        expected = (
            (PermissionError, "Authentication required"),
            (TimeoutError, "Router status unavailable"),
            (ValueError, "Malformed response"),
            (RuntimeError, "Unknown error"),
        )
        for exception_type, message in expected:
            with self.subTest(error_type=exception_type.__name__):
                provider = self.provider(error=exception_type(PRIVATE))
                window = self.window(provider)
                window.start_refresh()
                self.wait_until(lambda: provider.finished.is_set() and not window.refresh_controller.busy)
                self.assertEqual(window.status_label.text(), message)
                self.assertNotIn(PRIVATE, self.displayed_text(window))

    def test_thread_start_failure_is_friendly_and_leaves_no_busy_worker(self):
        provider = self.provider(known_snapshot())
        window = self.window(provider)
        with patch("sim_manager.ui.refresh.Thread.start", side_effect=RuntimeError(PRIVATE)):
            self.assertFalse(window.start_refresh())
        self.assertFalse(window.refresh_controller.busy)
        self.assertEqual(provider.calls, [])
        self.assertEqual(window.status_label.text(), "Unknown error")
        self.assertNotIn(PRIVATE, self.displayed_text(window))
        self.assertTrue(window.refresh_button.isEnabled())
        self.assertTrue(window.refresh_controller.shutdown(timeout=0.1))

    def test_cancel_after_worker_finishes_discards_undelivered_success(self):
        provider = self.provider(known_snapshot())
        window = self.window(provider)
        window.start_refresh()
        # Do not pump Qt until cancellation: exercise the worker/poll boundary.
        self.assertTrue(provider.finished.wait(0.5))
        window.refresh_controller.cancel()
        self.wait_until(lambda: not window.refresh_controller.busy)
        self.assertEqual(window.status_label.text(), "Refresh cancelled")
        self.assertEqual(self.values(window)["rsrp"], "—")

    def test_wrong_provider_result_becomes_friendly_error(self):
        provider = self.provider()
        provider.snapshot = {"Authorization": PRIVATE}
        window = self.window(provider)
        window.start_refresh()
        self.wait_until(lambda: provider.finished.is_set() and not window.refresh_controller.busy)
        self.assertNotIn(PRIVATE, self.displayed_text(window))
        self.assertEqual(self.values(window)["rsrp"], "—")
        self.assertTrue(window.status_label.text())

    def test_close_cancels_and_joins_cooperative_refresh_worker(self):
        provider = self.provider(known_snapshot(), blocked=True)
        window = self.window(provider)
        window.start_refresh()
        self.wait_until(provider.started.is_set)
        worker_ident, stop = provider.calls[0]
        started = time.monotonic()
        window.close()
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertTrue(stop.is_set())
        self.assertTrue(provider.finished.is_set())
        self.assertFalse(any(thread.ident == worker_ident for thread in threading.enumerate()))
        self.assertTrue(window.refresh_controller.shutdown(timeout=0.1))
        self.assertFalse(window.refresh_controller.start())

    def test_idle_shutdown_is_idempotent_and_prevents_future_refresh(self):
        provider = self.provider()
        window = self.window(provider)
        self.assertTrue(window.refresh_controller.shutdown(timeout=0.1))
        self.assertTrue(window.refresh_controller.shutdown(timeout=0.1))
        self.assertFalse(window.refresh_controller.start())
        self.assertEqual(provider.calls, [])

    def test_noncooperative_injected_worker_shutdown_is_bounded_and_discards_late_data(self):
        provider = self.provider(known_snapshot(), blocked=True, cooperative=False)
        window = self.window(provider)
        window.start_refresh()
        self.wait_until(provider.started.is_set)
        started = time.monotonic()
        self.assertFalse(window.refresh_controller.shutdown(timeout=0.01))
        self.assertLess(time.monotonic() - started, 0.5)
        # aboutToQuit/close/cleanup may repeat shutdown; a blocked injected
        # reader must not charge the full join allowance on every call.
        repeated = time.monotonic()
        self.assertFalse(window.refresh_controller.shutdown(timeout=1.0))
        self.assertLess(time.monotonic() - repeated, 0.5)
        self.assertFalse(window.refresh_controller.start())
        before = self.values(window)
        provider.release.set()
        self.wait_until(provider.finished.is_set)
        self.assertEqual(self.values(window), before)
        self.assertTrue(window.refresh_controller.shutdown(timeout=0.1))


if __name__ == "__main__":
    unittest.main()
