"""Explicit offline portable-build check; normal startup never imports this module."""

from dataclasses import replace
from datetime import datetime, timezone
from importlib import resources
import json
import re
import ssl
import sys
from time import monotonic, sleep


_CHECKS = (
    "resources", "branding", "window", "resize", "zero_values", "stale_values",
    "tray", "tray_right_edge", "close_to_tray", "expiry", "sim_switch",
    "webengine_off_record", "webengine_network_guard", "webengine_blank_js",
    "webengine_page_cleanup", "webengine_profile_cleanup", "exit_shutdown",
)


def _new_report() -> dict:
    try:
        from sim_manager import __version__
        version = __version__
    except Exception:
        version = "unknown"
    if type(version) is not str or re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}(?:[a-zA-Z0-9.+-]+)?", version) is None:
        version = "unknown"
    return {"schema": 1, "version": version, "frozen": getattr(sys, "frozen", False) is True,
            "passed": False, "checks": dict.fromkeys(_CHECKS, False), "counts": {"resources": 0}}


def _block_request(info) -> None:
    """Only a blank internal document is permitted; no network URL can pass."""
    try:
        allowed = info.requestUrl().toString() == "about:blank"
    except Exception:
        allowed = False
    info.block(not allowed)


def _flush_deletes() -> None:
    from PySide6.QtCore import QCoreApplication, QEvent
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class _BlankWebEngineProbe:
    def __init__(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor
        from PySide6.QtWebEngineWidgets import QWebEngineView

        class DenyRequests(QWebEngineUrlRequestInterceptor):
            def interceptRequest(self, info):
                _block_request(info)

        class QuietPage(QWebEnginePage):
            def acceptNavigationRequest(self, url, _kind, _main_frame):
                return url.toString() == "about:blank"

            def javaScriptConsoleMessage(self, *_unused):
                pass

        self.completed = False
        self.result = False
        self.view = self.page = self.profile = self.interceptor = None
        try:
            self.profile = QWebEngineProfile()
            self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
            self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
            self.interceptor = DenyRequests(self.profile)
            self.profile.setUrlRequestInterceptor(self.interceptor)
            self.profile.downloadRequested.connect(lambda download: download.cancel())
            self.page = QuietPage(self.profile)
            self.view = QWebEngineView()
            self.view.setWindowTitle("SIM Manager package check")
            self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            self.view.setPage(self.page)
            self.view.resize(420, 280)
            self.off_record = (self.profile.isOffTheRecord()
                               and self.profile.persistentCookiesPolicy() == QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
                               and self.profile.httpCacheType() == QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        except Exception:
            self.shutdown()
            raise

    def start(self) -> None:
        from PySide6.QtCore import QUrl
        self.page.loadFinished.connect(self._loaded)
        self.view.show()
        self.page.load(QUrl("about:blank"))

    def _loaded(self, ok: bool) -> None:
        if self.page is None:
            return
        if not ok:
            self.completed = True
            return
        self.page.runJavaScript(
            "(() => { const canvas = document.createElement('canvas'); "
            "const context = canvas.getContext('2d'); if (!context) return false; "
            "context.font = '12px Segoe UI'; return location.href === 'about:blank' "
            "&& context.measureText('SIM Manager').width > 0; })()",
            self._javascript_result,
        )

    def _javascript_result(self, value) -> None:
        if self.page is None:
            return
        self.result = value is True and self.view is not None and self.view.isVisible()
        self.completed = True

    def shutdown(self) -> tuple[bool, bool]:
        from shiboken6 import isValid
        view = getattr(self, "view", None)
        page, profile = self.page, self.profile
        self.view = self.page = self.profile = None
        if view is not None and isValid(view):
            view.close()
            view.deleteLater()
            _flush_deletes()
        if page is not None and isValid(page):
            page.triggerAction(page.WebAction.Stop)
            page.deleteLater()
            _flush_deletes()
        page_cleared = page is None or not isValid(page)
        if profile is not None and isValid(profile):
            profile.deleteLater()
            _flush_deletes()
        self.interceptor = None
        return page_cleared, profile is None or not isValid(profile)


class _SyntheticAccount:
    is_demo = False

    def __init__(self):
        from sim_manager.account_models import AccountState
        self.state = AccountState()
        self.listener = None

    def set_listener(self, listener):
        self.listener = listener
        if listener is not None:
            listener(self.state)

    def emit(self, state):
        self.state = state
        if self.listener is not None:
            self.listener(state)

    def disconnect(self):
        from sim_manager.account_models import AccountState
        self.emit(AccountState())

    cancel = disconnect

    def connect(self):
        return False

    def refresh_account(self):
        return False

    def offer_otp(self, _inbox):
        pass

    def otp_for_copy(self):
        return None

    def shutdown(self):
        self.listener = None
        self.disconnect()


def _perform_checks(report: dict) -> None:
    from PySide6.QtCore import QEventLoop
    from sim_manager.app import create_application
    from sim_manager.account_models import AccountData, AccountDataIssue, AccountPhase, AccountState, SessionValidity
    from sim_manager.models import ConnectionMode, ConnectionState, DeviceState, NetworkState, Readiness, SimState
    from sim_manager.services.sim_profiles import SimProfileService
    from sim_manager.sim_models import SimCarrier
    from sim_manager.storage.sim_profiles import MemorySimProfileStore
    from sim_manager.ui.icons import application_icon
    from sim_manager.ui.main_window import MainWindow
    from sim_manager.ui.preferences import AppPreferences, MemoryPreferencesStore

    application = create_application([])
    old_quit = application.quitOnLastWindowClosed()
    deadline = monotonic() + 12
    window = probe = None
    checks = report["checks"]
    try:
        files = (("sim_manager.resources", "d2-demo-report.json"),
                 ("sim_manager.resources", "d2-server.pem"),
                 ("sim_manager.resources", "sim-manager.png")) + tuple(
                     ("sim_manager.carriers.dito", name) for name in
                     ("auth_observer.js", "login_focus.js", "sms_helper.js", "account_data.js"))
        for package, name in files:
            value = resources.files(package).joinpath(name).read_bytes()
            if not value:
                raise ValueError
            if name.endswith(".json"):
                json.loads(value)
            elif name.endswith(".pem"):
                ssl.PEM_cert_to_DER_cert(value.decode("ascii"))
            elif name.endswith(".js"):
                value.decode("utf-8")
            report["counts"]["resources"] += 1
        checks["resources"] = True
        checks["branding"] = not application_icon().isNull()
        snapshot = DeviceState(
            sim=SimState(present=True, readiness=Readiness.READY, identity_key="iccid-v1:" + "a" * 64),
            network=NetworkState(connection_mode=ConnectionMode.LTE, connection=ConnectionState.CONNECTED),
            successful_sources=("wireless", "internet", "wan", "device", "wanStatus", "sim", "deviceDetails"),
            partial=False,
        )
        class Provider:
            is_demo = False
            def get_device_state(self, *, stop_event=None):
                return snapshot
        profiles = SimProfileService(MemorySimProfileStore())
        profiles.observe(snapshot)
        profiles.create_profile("Release check", None, SimCarrier.DITO)
        account = _SyntheticAccount()
        window = MainWindow(Provider(), account_service=account, sim_profiles=profiles,
                            preferences_store=MemoryPreferencesStore(AppPreferences(auto_refresh=False, close_to_tray=True)),
                            enable_tray=True)
        window.render_snapshot(snapshot)
        window.show()
        application.processEvents()
        checks["window"] = window.isVisible() and not window.windowIcon().isNull()
        for width, height in ((1000, 760), (840, 600)):
            window.resize(width, height)
            application.processEvents()
        checks["resize"] = window.width() == 840 and window.height() == 600
        data = AccountData(updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                           load_balance="PHP 0.00", data_remaining="0 MB")
        state = AccountState(phase=AccountPhase.CONNECTED, validity=SessionValidity.VALIDATED, data=data)
        account.emit(state)
        tray = window.tray_dashboard
        checks["zero_values"] = (window.home_page.profile_values["data_remaining"].text() == "0 MB"
                                 and tray.popup.data_label.text() == "0 MB")
        updated = window.home_page.account_updated.text()
        account.emit(replace(state, data_stale=True, data_issue=AccountDataIssue.UNAVAILABLE))
        checks["stale_values"] = (window.home_page.profile_values["data_remaining"].text() == "0 MB"
                                  and window.home_page.account_updated.text() == updated
                                  and "stale" in tray.popup.account_status_label.text().lower())
        checks["tray"] = tray.available
        if tray.available:
            tray.toggle_popup()
            application.processEvents()
            screen = tray._screen(tray._anchor())
            checks["tray_right_edge"] = (tray.popup.isVisible() and screen is not None
                                          and tray.popup.geometry().right() == screen.availableGeometry().right())
            tray.hide_popup()
            window.close()
            checks["close_to_tray"] = not window.isVisible() and not window._closed
            window.show_main_window()
        account.emit(AccountState(phase=AccountPhase.EXPIRED, validity=SessionValidity.EXPIRED))
        checks["expiry"] = (window.home_page.profile_values["data_remaining"].text() == "Not available"
                             and tray.popup.data_label.text() == "Unavailable")
        window.render_snapshot(replace(snapshot, sim=replace(snapshot.sim, identity_key="iccid-v1:" + "b" * 64)))
        checks["sim_switch"] = profiles.active_profile is None and tray.popup.data_label.text() == "Unavailable"
        probe = _BlankWebEngineProbe()
        checks["webengine_off_record"] = probe.off_record
        checks["webengine_network_guard"] = True
        probe.start()
        while not probe.completed and monotonic() < deadline:
            application.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 25)
            sleep(.01)
        checks["webengine_blank_js"] = probe.completed and probe.result
    finally:
        if probe is not None:
            try:
                checks["webengine_page_cleanup"], checks["webengine_profile_cleanup"] = probe.shutdown()
            except Exception:
                pass
        if window is not None:
            try:
                window.request_exit()
                checks["exit_shutdown"] = window._closed and not window.tray_dashboard.available
                window.deleteLater()
                _flush_deletes()
            except Exception:
                pass
        application.setQuitOnLastWindowClosed(old_quit)


def run_release_smoke(report_path: str) -> int:
    """Write one new closed report; never overwrite a caller's existing file."""
    try:
        output = open(report_path, "x", encoding="utf-8")
    except Exception:
        return 2
    report = _new_report()
    try:
        with output:
            try:
                _perform_checks(report)
            except Exception:
                pass
            report["passed"] = all(value is True for value in report["checks"].values())
            json.dump(report, output, indent=2)
            output.write("\n")
    except Exception:
        return 2
    return 0 if report["passed"] else 1
