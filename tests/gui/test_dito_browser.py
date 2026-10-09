"""Offline DITO browser boundaries; fake pages never contact MyDITO."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
import os
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QUrl, Signal
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineScript, QWebEngineSettings
from PySide6.QtWidgets import QApplication, QWidget
from shiboken6 import isValid

from sim_manager.account_models import AuthEvent
from sim_manager.carriers.dito import browser


PRIVATE = "SYNTHETIC_AUTH_SECRET_DO_NOT_FORWARD"


class FakeSettings:
    def __init__(self):
        self.attributes = {}
        self.unknown = None

    def setAttribute(self, attribute, enabled):
        self.attributes[attribute] = enabled

    def setUnknownUrlSchemePolicy(self, policy):
        self.unknown = policy


class FakeScripts:
    def __init__(self):
        self.items = []

    def insert(self, script):
        self.items.append(script)


class FakeProfile(QObject):
    downloadRequested = Signal(object)
    PersistentCookiesPolicy = QWebEngineProfile.PersistentCookiesPolicy
    HttpCacheType = QWebEngineProfile.HttpCacheType
    PersistentPermissionsPolicy = QWebEngineProfile.PersistentPermissionsPolicy

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cookies = self.cache = self.permissions = self.interceptor = None
        self.spell_check = True

    def isOffTheRecord(self):
        return True

    def storageName(self):
        return ""

    def setPersistentCookiesPolicy(self, policy):
        self.cookies = policy

    def setHttpCacheType(self, policy):
        self.cache = policy

    def setPersistentPermissionsPolicy(self, policy):
        self.permissions = policy

    def setSpellCheckEnabled(self, enabled):
        self.spell_check = enabled

    def setUrlRequestInterceptor(self, interceptor):
        self.interceptor = interceptor


class FakePage(QObject):
    certificateError = Signal(object)
    permissionRequested = Signal(object)
    fileSystemAccessRequested = Signal(object)
    registerProtocolHandlerRequested = Signal(object)
    renderProcessTerminated = Signal(object, int)
    loadStarted = Signal()
    loadFinished = Signal(bool)
    urlChanged = Signal(QUrl)

    def __init__(self, profile, parent):
        super().__init__(parent)
        self.profile = profile
        self._settings = FakeSettings()
        self._scripts = FakeScripts()
        self._url = QUrl()
        self.loaded_url = None
        self.result = "none"
        self.pending = False
        self.callbacks = []
        self.probes = []
        self.actions = []

    def settings(self):
        return self._settings

    def scripts(self):
        return self._scripts

    def load(self, url):
        self.loaded_url = self._url = url

    def url(self):
        return self._url

    def runJavaScript(self, source, callback):
        self.probes.append(source)
        if self.pending:
            self.callbacks.append(callback)
        else:
            callback(self.result)

    def triggerAction(self, action):
        self.actions.append(action)


class FakeView(QWidget):
    def setPage(self, page):
        self.browser_page = page


class DeniedRequest:
    def __init__(self):
        self.denied = False

    def deny(self):
        self.denied = True

    reject = deny
    rejectCertificate = deny
    cancel = deny


class DitoBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        cls.application.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.guards = ExitStack()
        self.addCleanup(self.guards.close)
        for target in ("socket.socket", "socket.create_connection", "subprocess.Popen", "webbrowser.open"):
            self.guards.enter_context(patch(target, side_effect=AssertionError("External I/O forbidden")))
        self.guards.enter_context(patch.dict(os.environ, {
            "QTWEBENGINE_REMOTE_DEBUGGING": "",
            "QTWEBENGINE_DISABLE_SANDBOX": "",
            "QTWEBENGINE_CHROMIUM_FLAGS": "",
        }))
        self.guards.enter_context(patch.object(browser, "QWebEngineProfile", FakeProfile))
        self.guards.enter_context(patch.object(browser, "_DitoPage", FakePage))
        self.guards.enter_context(patch.object(browser, "QWebEngineView", FakeView))
        self.events = []
        self.surface = browser.DitoBrowserSurface()
        # Real widgets are used, but the simulated browser never loads a page.
        self.guards.enter_context(patch.object(self.surface, "show"))
        self.addCleanup(self.clean_surface)

    def clean_surface(self):
        self.surface.close()
        self.flush_deletes()
        self.surface.deleteLater()
        self.flush_deletes()

    def flush_deletes(self):
        for _ in range(3):
            self.application.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def opened(self):
        self.surface.open(self.events.append)
        return self.surface._page, self.surface._profile, self.surface._dialog

    def loaded(self):
        page, profile, dialog = self.opened()
        page.loadFinished.emit(True)
        return page, profile, dialog

    def authenticate(self, page):
        page._url = QUrl("https://my.dito.ph/pto/home")
        page.result = "authenticated"
        self.surface._probe()

    def test_open_loads_only_official_flow_with_unnamed_memory_profile(self):
        page, profile, dialog = self.opened()
        self.assertEqual(page.loaded_url, QUrl("https://my.dito.ph/"))
        self.assertEqual(profile.cookies, QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self.assertEqual(profile.cache, QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        self.assertEqual(profile.permissions, QWebEngineProfile.PersistentPermissionsPolicy.AskEveryTime)
        self.assertFalse(profile.spell_check)
        self.assertEqual(dialog.windowModality(), browser.Qt.WindowModality.NonModal)
        self.assertIn("Official MyDITO", dialog.windowTitle())
        self.assertEqual(self.events, [])
        self.assertTrue(self.surface._load_timer.isActive())
        self.assertEqual(self.surface._load_timer.interval(), 30_000)

    def test_observer_is_installed_before_navigation_once_in_main_world(self):
        page, _, _ = self.opened()
        self.assertEqual(len(page.scripts().items), 1)
        script = page.scripts().items[0]
        self.assertEqual(script.injectionPoint(), QWebEngineScript.InjectionPoint.DocumentCreation)
        self.assertEqual(script.worldId(), QWebEngineScript.ScriptWorldId.MainWorld)
        self.assertFalse(script.runsOnSubFrames())
        self.assertEqual(script.sourceCode(), browser.observer_source())

    def test_browser_settings_deny_unneeded_privileged_actions(self):
        page, profile, _ = self.opened()
        settings = page.settings()
        self.assertTrue(settings.attributes)
        self.assertTrue(all(value is False for value in settings.attributes.values()))
        self.assertEqual(settings.unknown, QWebEngineSettings.UnknownUrlSchemePolicy.DisallowUnknownUrlSchemes)
        self.assertIsInstance(profile.interceptor, browser._AuthRequests)

    def test_download_permissions_files_and_protocol_registration_are_denied(self):
        page, profile, _ = self.opened()
        for signal in (
            profile.downloadRequested, page.permissionRequested,
            page.fileSystemAccessRequested, page.registerProtocolHandlerRequested,
        ):
            request = DeniedRequest()
            signal.emit(request)
            self.assertTrue(request.denied)
        self.assertEqual(self.events, [])

    def test_success_hides_dialog_retains_profile_and_publishes_once(self):
        page, profile, dialog = self.loaded()
        dialog.show()
        self.authenticate(page)
        self.assertEqual(self.events, [AuthEvent.AUTHENTICATED])
        self.assertFalse(dialog.isVisible())
        self.assertTrue(isValid(profile))
        self.assertIs(self.surface._profile, profile)
        self.surface._probe()
        self.assertEqual(self.events, [AuthEvent.AUTHENTICATED])
        self.assertTrue(self.surface._poll_timer.isActive())
        self.assertFalse(self.surface._load_timer.isActive())

    def test_home_route_alone_does_not_authenticate(self):
        page, _, _ = self.loaded()
        page._url = QUrl("https://my.dito.ph/pto/home")
        self.surface._probe()
        self.assertEqual(self.events, [])
        self.assertFalse(self.surface._authenticated)

    def test_success_token_on_other_route_fails_closed(self):
        page, _, _ = self.loaded()
        page.result = "authenticated"
        self.surface._probe()
        self.assertEqual(self.events, [AuthEvent.UNSUPPORTED])
        self.assertTrue(self.surface._closed)

    def test_rejected_login_keeps_official_page_for_manual_retry(self):
        page, profile, dialog = self.loaded()
        dialog.show()
        page.result = "rejected"
        self.surface._probe()
        self.surface._probe()
        self.assertEqual(self.events, [AuthEvent.REJECTED])
        self.assertIs(self.surface._profile, profile)
        self.assertTrue(dialog.isVisible())
        page.result = "none"
        self.surface._probe()
        page.result = "rejected"
        self.surface._probe()
        self.assertEqual(self.events, [AuthEvent.REJECTED, AuthEvent.REJECTED])
        self.authenticate(page)
        self.assertEqual(self.events[-1], AuthEvent.AUTHENTICATED)
        self.assertFalse(self.surface._closed)

    def test_verified_expiry_closes_session_and_requires_new_profile(self):
        page, profile, _ = self.loaded()
        self.authenticate(page)
        page.result = "expired"
        self.surface._probe()
        self.assertEqual(self.events, [AuthEvent.AUTHENTICATED, AuthEvent.EXPIRED])
        self.assertIsNone(self.surface._profile)
        self.flush_deletes()
        self.assertFalse(isValid(profile))
        _, replacement, _ = self.opened()
        self.assertIsNot(replacement, profile)

    def test_unestablished_expiry_is_unsupported(self):
        page, _, _ = self.loaded()
        page.result = "expired"
        self.surface._probe()
        self.assertEqual(self.events, [AuthEvent.UNSUPPORTED])

    def test_observed_logout_discards_the_local_context(self):
        page, _, _ = self.loaded()
        self.authenticate(page)
        page.result = "disconnected"
        self.surface._probe()
        self.assertEqual(self.events, [AuthEvent.AUTHENTICATED, AuthEvent.DISCONNECTED])
        self.assertTrue(self.surface._closed)

    def test_full_navigation_back_to_sign_in_disconnects_without_expiry_claim(self):
        page, _, _ = self.loaded()
        self.authenticate(page)
        page.result = "none"
        page._url = QUrl("https://my.dito.ph/")
        page.urlChanged.emit(page._url)
        self.assertEqual(self.events, [AuthEvent.AUTHENTICATED, AuthEvent.DISCONNECTED])
        self.assertTrue(self.surface._closed)

    def test_new_full_document_load_invalidates_previous_observer_proof(self):
        page, _, _ = self.loaded()
        self.authenticate(page)
        page.loadStarted.emit()
        self.assertEqual(self.events, [AuthEvent.AUTHENTICATED, AuthEvent.DISCONNECTED])
        self.assertTrue(self.surface._closed)

    def test_initial_document_load_has_bounded_load_deadline_without_disconnect(self):
        page, _, _ = self.opened()
        page.loadStarted.emit()
        self.assertEqual(self.events, [])
        self.assertFalse(self.surface._closed)
        self.assertTrue(self.surface._load_timer.isActive())

    def test_explicit_programmatic_close_is_silent_and_idempotent(self):
        self.loaded()
        self.surface.close()
        self.surface.close()
        self.surface.show()
        self.assertEqual(self.events, [])
        self.assertTrue(self.surface._closed)
        self.assertFalse(self.surface._poll_timer.isActive())

    def test_user_dialog_cancel_emits_only_disconnected_and_clears_context(self):
        _, profile, dialog = self.loaded()
        dialog.reject()
        self.assertEqual(self.events, [AuthEvent.DISCONNECTED])
        self.assertTrue(self.surface._closed)
        self.assertIsNone(self.surface._profile)
        self.flush_deletes()
        self.assertFalse(isValid(profile))

    def test_initial_page_load_deadline_is_closed_and_not_a_login_ttl(self):
        self.opened()
        self.surface._load_timer.timeout.emit()
        self.assertEqual(self.events, [AuthEvent.UNAVAILABLE])
        self.assertTrue(self.surface._closed)

    def test_pending_probe_does_not_overlap_and_late_callback_after_close_is_ignored(self):
        page, _, _ = self.opened()
        page.pending = True
        page.loadFinished.emit(True)
        self.surface._probe()
        self.assertEqual(len(page.callbacks), 1)
        self.assertEqual(len(page.probes), 1)
        callback = page.callbacks[0]
        self.surface.close()
        callback("authenticated")
        self.assertEqual(self.events, [])

    def test_late_callback_from_previous_generation_does_not_change_new_sign_in(self):
        page, _, _ = self.opened()
        page.pending = True
        page.loadFinished.emit(True)
        callback = page.callbacks[0]
        self.surface.close()
        replacement, _, _ = self.opened()
        callback("unsupported")
        self.assertIs(self.surface._page, replacement)
        self.assertFalse(self.surface._closed)
        self.assertEqual(self.events, [])

    def test_probe_deadline_closes_without_retries(self):
        page, _, _ = self.opened()
        page.pending = True
        page.loadFinished.emit(True)
        self.surface._probe_timer.timeout.emit()
        self.assertEqual(self.events, [AuthEvent.UNAVAILABLE])
        self.assertEqual(len(page.probes), 1)
        page.callbacks[0]("none")
        self.assertEqual(self.events, [AuthEvent.UNAVAILABLE])

    def test_certificate_failure_is_rejected_without_ignore(self):
        page, _, _ = self.opened()
        request = DeniedRequest()
        page.certificateError.emit(request)
        self.assertTrue(request.denied)
        self.assertEqual(self.events, [AuthEvent.UNAVAILABLE])

    def test_foreign_spa_or_full_navigation_is_unsupported(self):
        page, _, _ = self.loaded()
        page.urlChanged.emit(QUrl("https://example.invalid/?token=" + PRIVATE))
        self.assertEqual(self.events, [AuthEvent.UNSUPPORTED])

    def test_browser_error_and_unknown_probe_values_never_reach_output(self):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            page, _, _ = self.loaded()
            page.result = {"cookie": PRIVATE, "token": PRIVATE, "otp": "123456"}
            self.surface._probe()
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(self.events, [AuthEvent.UNSUPPORTED])
        self.surface.close()
        with redirect_stdout(output), redirect_stderr(output), patch.object(
            self.surface, "_build", side_effect=RuntimeError(PRIVATE),
        ):
            self.surface.open(self.events.append)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(self.events[-1], AuthEvent.UNAVAILABLE)

    def test_page_probe_exception_is_redacted(self):
        page, _, _ = self.loaded()
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output), patch.object(
            page, "runJavaScript", side_effect=RuntimeError(PRIVATE),
        ):
            self.surface._probe()
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(self.events, [AuthEvent.UNAVAILABLE])

    def test_page_is_destroyed_before_profile(self):
        page, profile, _ = self.loaded()
        order = []
        page.destroyed.connect(lambda: order.append("page"))
        profile.destroyed.connect(lambda: order.append("profile"))
        self.surface.close()
        self.flush_deletes()
        self.assertEqual(order, ["page", "profile"])

    def test_enabled_debugging_or_security_bypass_refuses_before_page_creation(self):
        for setting, value in (
            ("QTWEBENGINE_REMOTE_DEBUGGING", "9222"),
            ("QTWEBENGINE_DISABLE_SANDBOX", "1"),
            ("QTWEBENGINE_CHROMIUM_FLAGS", "--ignore-certificate-errors"),
            ("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-web-security"),
            ("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox"),
            ("QTWEBENGINE_CHROMIUM_FLAGS", "--remote-debugging-port=9222"),
        ):
            with self.subTest(setting=setting, value=value), patch.dict(os.environ, {setting: value}), patch.object(self.surface, "_build") as build:
                self.surface.open(self.events.append)
                build.assert_not_called()
                self.assertEqual(self.events[-1], AuthEvent.UNSUPPORTED)
                self.assertIsNone(self.surface._profile)


class DitoPageBoundaryTests(unittest.TestCase):
    def test_console_popup_and_file_chooser_values_are_discarded(self):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            browser._DitoPage.javaScriptConsoleMessage(None, None, PRIVATE, 1, PRIVATE)
        self.assertEqual(output.getvalue(), "")
        self.assertIsNone(browser._DitoPage.createWindow(None, None))
        self.assertEqual(browser._DitoPage.chooseFiles(None, None, [PRIVATE], [PRIVATE]), [])

    def test_navigation_policy_failure_is_closed_without_diagnostics(self):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output), patch.object(browser, "trusted_origin", side_effect=RuntimeError(PRIVATE)):
            allowed = browser._DitoPage.acceptNavigationRequest(None, QUrl("https://my.dito.ph/"), None, True)
        self.assertFalse(allowed)
        self.assertEqual(output.getvalue(), "")

    def test_request_interceptor_never_forwards_policy_exception(self):
        class Request:
            blocked = None

            def requestMethod(self):
                return b"POST"

            def requestUrl(self):
                return QUrl("https://my.dito.ph/ecare/webs/user/login")

            def block(self, blocked):
                self.blocked = blocked

        request = Request()
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output), patch.object(browser, "request_allowed", side_effect=RuntimeError(PRIVATE)):
            browser._AuthRequests.interceptRequest(None, request)
        self.assertTrue(request.blocked)
        self.assertEqual(output.getvalue(), "")


class RealBlankProfileTests(unittest.TestCase):
    def test_real_unnamed_profile_is_memory_only_without_loading_a_page(self):
        application = QApplication.instance() or QApplication([])
        profile = QWebEngineProfile(application)
        try:
            profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
            profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
            self.assertTrue(profile.isOffTheRecord())
            self.assertEqual(profile.storageName(), "")
            self.assertEqual(profile.persistentCookiesPolicy(), QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
            self.assertEqual(profile.httpCacheType(), QWebEngineProfile.HttpCacheType.MemoryHttpCache)
            # No page exists, no load call is made and no cookie values are read.
        finally:
            profile.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.assertFalse(isValid(profile))
