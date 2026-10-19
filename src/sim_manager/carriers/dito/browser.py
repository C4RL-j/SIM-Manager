"""Isolated MyDITO authentication surface; private browser state stays here.

The surface observes the official flow. It never reads input values, exports
cookies or makes a separate authentication request. Optional SMS assistance
fills only an explicitly chosen new code, without submitting the official form.
"""

from collections.abc import Callable
from importlib.resources import files
import json
from os import environ

from PySide6.QtCore import QObject, Qt, QTimer, QUrl
from PySide6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget
from shiboken6 import isValid

from sim_manager.account_models import AccountDataIssue, AccountDataResult, AuthEvent

from .account_data import account_result

from .auth_policy import (
    LOGIN_URL, PROBE_SOURCE, authenticated_route, observer_source,
    account_request_allowed, request_allowed, trusted_origin,
)


_LOAD_TIMEOUT_MS = 30_000
_PROBE_TIMEOUT_MS = 5_000
_POLL_INTERVAL_MS = 500
_HELPER_PROBE = "JSON.stringify(window.__simManagerDitoSmsHelper ? window.__simManagerDitoSmsHelper.observe() : null)"


class _AuthRequests(QWebEngineUrlRequestInterceptor):
    """A pure allowlist check; no URL, body or header is retained or logged."""

    def __init__(self, parent=None, *, account_data: bool = False) -> None:
        super().__init__(parent)
        self._account_data = account_data

    def interceptRequest(self, info) -> None:
        try:
            method = bytes(info.requestMethod()).decode("ascii", errors="strict")
            policy = account_request_allowed if getattr(self, "_account_data", False) else request_allowed
            allowed = policy(info.requestUrl().toString(), method)
        except Exception:
            allowed = False
        info.block(not allowed)


class _DitoPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, navigation_type, is_main_frame) -> bool:
        # Frames and top-level navigation are both restricted to MyDITO.
        try:
            return trusted_origin(url.toString())
        except Exception:
            return False

    def javaScriptConsoleMessage(self, level, message, line_number, source_id) -> None:
        # Qt's default implementation logs site messages. Discard all arguments.
        pass

    def createWindow(self, window_type):
        return None

    def chooseFiles(self, mode, old_files, accepted_mime_types):
        return []


class DitoBrowserSurface(QObject):
    """A nonmodal official sign-in window with an in-memory session lifetime."""

    def __init__(
        self, parent: QObject | None = None, *, helper_panel: QWidget | None = None,
        account_number: Callable[[], str | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._callback: Callable[[AuthEvent], None] | None = None
        self._closed = True
        self._generation = 0
        self._authenticated = False
        self._last_observation = "none"
        self._probe_pending = False
        self._dialog = None
        self._view = None
        self._page = None
        self._profile = None
        self._interceptor = None
        self._helper_panel = helper_panel
        self._helper_request = 0
        self._helper_revision = 0
        self._helper_serial = 0
        self._helper_probe_pending = False
        self._account_number = account_number
        self._account_callback: Callable[[AccountDataResult], None] | None = None
        self._account_expected: str | None = None
        self._account_request = 0
        self._account_probe_pending = False
        self._account_timer = QTimer(self)
        self._account_timer.setInterval(250)
        self._account_timer.timeout.connect(self._probe_account)
        self._account_deadline = QTimer(self)
        self._account_deadline.setSingleShot(True)
        self._account_deadline.timeout.connect(
            lambda: self._complete_account(AccountDataResult(issue=AccountDataIssue.UNAVAILABLE)),
        )
        self._helper_timer = QTimer(self)
        self._helper_timer.setInterval(250)
        self._helper_timer.timeout.connect(self._probe_helper)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._probe)
        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.timeout.connect(lambda: self._finish(AuthEvent.UNAVAILABLE))
        self._probe_timer = QTimer(self)
        self._probe_timer.setSingleShot(True)
        self._probe_timer.timeout.connect(lambda: self._finish(AuthEvent.UNAVAILABLE))

    def open(self, callback: Callable[[AuthEvent], None]) -> None:
        if not self._closed:
            self.show()
            return
        if not callable(callback):
            raise TypeError("An authentication event callback is required.")
        self._generation += 1
        self._closed = False
        self._authenticated = False
        self._last_observation = "none"
        self._callback = callback
        try:
            flags = environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
            if environ.get("QTWEBENGINE_REMOTE_DEBUGGING") or environ.get("QTWEBENGINE_DISABLE_SANDBOX") or any(
                flag in flags for flag in (
                    "--remote-debugging", "--ignore-certificate-errors",
                    "--disable-web-security", "--no-sandbox",
                )
            ):
                self._finish(AuthEvent.UNSUPPORTED)
                return
            self._build()
            self._load_timer.start(_LOAD_TIMEOUT_MS)
            self._page.load(QUrl(LOGIN_URL))
            self.show()
        except Exception:
            # Browser errors can include URLs or site contents. Publish a closed
            # event rather than propagating exception text or its traceback.
            self._finish(AuthEvent.UNAVAILABLE)

    def _build(self) -> None:
        owner = self.parent() if isinstance(self.parent(), QWidget) else None
        self._dialog = QDialog(owner)
        self._dialog.setWindowTitle("Sign in with DITO · Official MyDITO")
        self._dialog.setWindowModality(Qt.WindowModality.NonModal)
        self._dialog.resize(480, 520)
        self._dialog.setMinimumSize(420, 500)
        layout = QVBoxLayout(self._dialog)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)
        heading = QLabel("Authenticate directly with DITO at https://my.dito.ph")
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setWordWrap(True)
        layout.addWidget(heading)
        note = QLabel("Enter sign-in details and security challenges only on the official page. This session is kept in memory.")
        note.setTextFormat(Qt.TextFormat.PlainText)
        note.setWordWrap(True)
        layout.addWidget(note)
        if self._helper_panel is not None:
            layout.addWidget(self._helper_panel)
            # Preserve the compact web viewport; add only the native helper's
            # height, including its stable action row, to the existing shell.
            extra_height = max(0, self._helper_panel.sizeHint().height()) + layout.spacing()
            self._dialog.resize(480, 520 + extra_height)
            self._dialog.setMinimumSize(420, 500 + extra_height)
            self._helper_panel.fill_requested.connect(self.fill_otp)
        self._profile = QWebEngineProfile(self)
        if not self._profile.isOffTheRecord() or self._profile.storageName():
            raise RuntimeError("An isolated browser session is required.")
        self._profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self._profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        self._profile.setPersistentPermissionsPolicy(QWebEngineProfile.PersistentPermissionsPolicy.AskEveryTime)
        self._profile.setSpellCheckEnabled(False)
        self._profile.downloadRequested.connect(lambda download: download.cancel())
        if self._account_number is not None:
            self._interceptor = _AuthRequests(self._profile, account_data=True)
        else:
            self._interceptor = _AuthRequests(self._profile)
        self._profile.setUrlRequestInterceptor(self._interceptor)
        self._page = _DitoPage(self._profile, self)
        settings = self._page.settings()
        for attribute in (
            QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows,
            QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard,
            QWebEngineSettings.WebAttribute.JavascriptCanPaste,
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,
            QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,
            QWebEngineSettings.WebAttribute.PluginsEnabled,
            QWebEngineSettings.WebAttribute.FullScreenSupportEnabled,
            QWebEngineSettings.WebAttribute.ScreenCaptureEnabled,
            QWebEngineSettings.WebAttribute.HyperlinkAuditingEnabled,
            QWebEngineSettings.WebAttribute.ErrorPageEnabled,
            QWebEngineSettings.WebAttribute.DnsPrefetchEnabled,
            QWebEngineSettings.WebAttribute.PdfViewerEnabled,
        ):
            settings.setAttribute(attribute, False)
        settings.setUnknownUrlSchemePolicy(QWebEngineSettings.UnknownUrlSchemePolicy.DisallowUnknownUrlSchemes)
        script = QWebEngineScript()
        script.setName("SIM Manager authentication observer")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode(observer_source())
        self._page.scripts().insert(script)
        if self._account_number is not None:
            self._install_account_reader()
        self._install_login_presentation()
        if self._helper_panel is not None:
            self._install_sms_helper()
        self._page.certificateError.connect(self._certificate_error)
        self._page.permissionRequested.connect(lambda permission: permission.deny())
        self._page.fileSystemAccessRequested.connect(lambda request: request.reject())
        self._page.registerProtocolHandlerRequested.connect(lambda request: request.reject())
        self._page.renderProcessTerminated.connect(lambda status, code: self._finish(AuthEvent.UNAVAILABLE))
        self._page.loadStarted.connect(self._load_started)
        self._page.loadFinished.connect(self._loaded)
        self._page.urlChanged.connect(self._url_changed)
        self._view = QWebEngineView(self._dialog)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._view.setPage(self._page)
        self._view.setZoomFactor(0.88)
        layout.addWidget(self._view, 1)
        cancel = QPushButton("Cancel sign-in")
        cancel.clicked.connect(self._user_cancel)
        layout.addWidget(cancel)
        self._dialog.finished.connect(self._user_cancel)

    def _install_login_presentation(self) -> None:
        """Optional CSS presentation; any failure leaves the official full page."""
        try:
            source = files("sim_manager.carriers.dito").joinpath("login_focus.js").read_text(encoding="utf-8")
            if not source:
                return
            script = QWebEngineScript()
            script.setName("SIM Manager login presentation")
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
            script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
            script.setRunsOnSubFrames(False)
            script.setSourceCode(source)
            self._page.scripts().insert(script)
        except Exception:
            # Styling must never turn a readable login page into an auth error.
            pass

    def show(self) -> None:
        if self._closed or self._dialog is None:
            return
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()

    def _install_account_reader(self) -> None:
        try:
            source = files("sim_manager.carriers.dito").joinpath("account_data.js").read_text(encoding="utf-8")
            script = QWebEngineScript()
            script.setName("SIM Manager read-only account data")
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            script.setRunsOnSubFrames(False)
            script.setSourceCode(source)
            self._page.scripts().insert(script)
        except Exception:
            # Optional data access cannot change the original login flow.
            pass

    def refresh_account(self, callback: Callable[[AccountDataResult], None]) -> bool:
        """Use the official page's existing client; never export its session."""
        if (self._closed or not self._authenticated or self._page is None
                or self._account_callback is not None or not callable(callback)
                or self._account_number is None
                or not authenticated_route(self._page.url().toString())):
            return False
        try:
            expected = self._account_number()
        except Exception:
            expected = None
        if (type(expected) is not str or not 10 <= len(expected) <= 14
                or any(char not in "+0123456789" for char in expected)):
            try:
                callback(AccountDataResult(issue=AccountDataIssue.ACCOUNT_MISMATCH))
            except Exception:
                pass
            return True
        self._account_request += 1
        request, generation = self._account_request, self._generation
        self._account_callback = callback
        self._account_expected = expected
        self._account_probe_pending = False
        self._account_deadline.start(30_000)
        source = (
            "Boolean(window.__simManagerDitoAccountData && "
            "window.__simManagerDitoAccountData.start("
            + str(request) + "," + json.dumps(expected) + "))"
        )
        try:
            self._page.runJavaScript(
                source, QWebEngineScript.ScriptWorldId.MainWorld,
                lambda result: self._account_started(result, generation, request),
            )
        except Exception:
            self._complete_account(AccountDataResult(issue=AccountDataIssue.UNAVAILABLE))
        return True

    def _account_started(self, result, generation: int, request: int) -> None:
        if not self._account_current(generation, request):
            return
        if result is not True:
            self._complete_account(AccountDataResult(issue=AccountDataIssue.UNSUPPORTED))
            return
        self._account_timer.start()
        self._probe_account()

    def _account_current(self, generation: int, request: int) -> bool:
        return (not self._closed and self._authenticated and self._page is not None
                and generation == self._generation and request == self._account_request
                and self._account_callback is not None)

    def _probe_account(self) -> None:
        if (not self._account_current(self._generation, self._account_request)
                or self._account_probe_pending):
            return
        try:
            current = self._account_number()
        except Exception:
            current = None
        if current != self._account_expected:
            self._complete_account(AccountDataResult(issue=AccountDataIssue.ACCOUNT_MISMATCH))
            return
        if not authenticated_route(self._page.url().toString()):
            self._complete_account(AccountDataResult(issue=AccountDataIssue.EXPIRED))
            return
        self._account_probe_pending = True
        generation, request = self._generation, self._account_request
        source = (
            "JSON.stringify(window.__simManagerDitoAccountData ? "
            "window.__simManagerDitoAccountData.poll(" + str(request) + ") : null)"
        )
        try:
            self._page.runJavaScript(
                source, QWebEngineScript.ScriptWorldId.MainWorld,
                lambda result: self._account_observed(result, generation, request),
            )
        except Exception:
            self._account_probe_pending = False
            self._complete_account(AccountDataResult(issue=AccountDataIssue.UNAVAILABLE))

    def _account_observed(self, value, generation: int, request: int) -> None:
        if not self._account_current(generation, request):
            return
        self._account_probe_pending = False
        try:
            expected = self._account_number()
        except Exception:
            expected = None
        if expected != self._account_expected:
            self._complete_account(AccountDataResult(issue=AccountDataIssue.ACCOUNT_MISMATCH))
            return
        if not authenticated_route(self._page.url().toString()):
            self._complete_account(AccountDataResult(issue=AccountDataIssue.EXPIRED))
            return
        result = account_result(value, request)
        if result is not None:
            self._complete_account(result)

    def _complete_account(self, result: AccountDataResult) -> None:
        callback, self._account_callback = self._account_callback, None
        self._account_expected = None
        self._account_probe_pending = False
        self._account_timer.stop()
        self._account_deadline.stop()
        if self._page is not None and not self._closed:
            try:
                self._page.runJavaScript(
                    "window.__simManagerDitoAccountData && window.__simManagerDitoAccountData.stop()",
                    QWebEngineScript.ScriptWorldId.MainWorld,
                )
            except Exception:
                pass
        if callback is not None and not self._closed:
            try:
                callback(result)
            except Exception:
                pass

    def _install_sms_helper(self) -> None:
        """Optional helper; installation failure cannot change authentication."""
        try:
            source = files("sim_manager.carriers.dito").joinpath("sms_helper.js").read_text(encoding="utf-8")
            script = QWebEngineScript()
            script.setName("SIM Manager explicit SMS helper")
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
            script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
            script.setRunsOnSubFrames(False)
            script.setSourceCode(source)
            self._page.scripts().insert(script)
        except Exception:
            pass

    def _helper_call(self, method: str, *args) -> None:
        try:
            if self._helper_panel is not None:
                getattr(self._helper_panel, method)(*args)
        except Exception:
            # Optional helper errors and their private fields stay local.
            pass

    def _probe_helper(self) -> None:
        if (self._closed or self._authenticated or self._helper_panel is None
                or self._helper_probe_pending or self._page is None):
            return
        self._helper_probe_pending = True
        generation, revision = self._generation, self._helper_revision
        try:
            self._page.runJavaScript(
                _HELPER_PROBE, QWebEngineScript.ScriptWorldId.ApplicationWorld,
                lambda result: self._helper_observed(result, generation, revision),
            )
        except Exception:
            self._helper_probe_pending = False
            self._helper_call("set_fillable", False)

    def _helper_observed(self, result, generation: int, revision: int) -> None:
        if (self._closed or self._authenticated or generation != self._generation
                or revision != self._helper_revision):
            return
        self._helper_probe_pending = False
        try:
            if type(result) is not str or len(result) > 128:
                raise ValueError
            observed = json.loads(result)
            if (type(observed) is not dict or set(observed) != {"request", "fillable"}
                    or type(observed["request"]) is not int
                    or not 0 <= observed["request"] <= 2**53 - 1
                    or type(observed["fillable"]) is not bool):
                raise ValueError
            request = observed["request"]
            if request != self._helper_request:
                self._helper_request = request
                if request > 0:
                    # DOM counters restart on document navigation; the native
                    # watch identifier remains monotonic for this popup.
                    self._helper_serial += 1
                    self._helper_call("request_sms_code", self._helper_serial)
                else:
                    self._helper_call("stop")
            self._helper_call("set_fillable", observed["fillable"])
        except Exception:
            self._helper_call("set_fillable", False)

    def fill_otp(self, code: str) -> None:
        """Only a native explicit Fill OTP action invokes the original field."""
        if (self._closed or self._authenticated or self._page is None
                or self._helper_panel is None or self._helper_request <= 0
                or type(code) is not str or len(code) != 6
                or any(character not in "0123456789" for character in code)):
            self._helper_call("fill_result", False)
            return
        generation, request, revision = self._generation, self._helper_request, self._helper_revision
        source = (
            "Boolean(window.__simManagerDitoSmsHelper && "
            "window.__simManagerDitoSmsHelper.fill("
            + json.dumps(code) + "," + str(request) + "))"
        )
        try:
            self._page.runJavaScript(
                source, QWebEngineScript.ScriptWorldId.ApplicationWorld,
                lambda result: self._filled_otp(result, generation, request, revision),
            )
        except Exception:
            self._helper_call("fill_result", False)
        finally:
            code = source = None

    def _filled_otp(self, result, generation: int, request: int, revision: int) -> None:
        if (self._closed or self._authenticated or generation != self._generation
                or revision != self._helper_revision or request != self._helper_request):
            return
        self._helper_call("fill_result", result is True)

    def _revoke_helper(self, *, keep_request: bool = False) -> None:
        self._helper_revision += 1
        self._helper_probe_pending = False
        if not keep_request:
            self._helper_request = 0
        self._helper_call("set_fillable", False)
        self._helper_call("stop")

    def _certificate_error(self, error) -> None:
        error.rejectCertificate()
        self._finish(AuthEvent.UNAVAILABLE)

    def _loaded(self, ok: bool) -> None:
        if self._closed:
            return
        self._load_timer.stop()
        if ok is not True:
            self._finish(AuthEvent.UNAVAILABLE)
            return
        if self._page is None or not trusted_origin(self._page.url().toString()):
            self._finish(AuthEvent.UNSUPPORTED)
            return
        self._poll_timer.start()
        if self._helper_panel is not None:
            self._helper_timer.start()
        self._probe()

    def _load_started(self) -> None:
        if self._closed:
            return
        self._revoke_helper()
        if self._authenticated:
            # A new document has a fresh observer with no previous auth proof.
            # Disconnect locally instead of reporting an invented expiry or
            # silently trusting state that can no longer be checked safely.
            self._finish(AuthEvent.DISCONNECTED)
        else:
            self._load_timer.start(_LOAD_TIMEOUT_MS)

    def _url_changed(self, url: QUrl) -> None:
        if self._closed:
            return
        if not trusted_origin(url.toString()):
            self._finish(AuthEvent.UNSUPPORTED)
        elif self._authenticated and url.path() == "/" and not url.query() and not url.fragment():
            # A full document navigation starts a fresh observer. The Python
            # session still conservatively disconnects on the verified login
            # route without inventing a server-expiry reason.
            # The official data client returns to sign-in when authentication
            # is rejected. The enabled reader must make reauthentication clear.
            self._finish(AuthEvent.EXPIRED if self._account_number is not None else AuthEvent.DISCONNECTED)

    def _probe(self) -> None:
        if self._closed or self._probe_pending or self._page is None:
            return
        if not trusted_origin(self._page.url().toString()):
            self._finish(AuthEvent.UNSUPPORTED)
            return
        self._probe_pending = True
        generation = self._generation
        self._probe_timer.start(_PROBE_TIMEOUT_MS)
        try:
            self._page.runJavaScript(
                PROBE_SOURCE,
                lambda result: self._probe_finished(result, generation),
            )
        except Exception:
            self._finish(AuthEvent.UNAVAILABLE)

    def _probe_finished(self, result, generation: int) -> None:
        # Qt guarantees a callback even during page destruction. It is unsafe to
        # access that page then; revoked generations return before touching it.
        if self._closed or generation != self._generation:
            return
        self._probe_pending = False
        self._probe_timer.stop()
        if type(result) is not str or result not in {"none", "authenticated", "rejected", "expired", "unsupported", "disconnected"}:
            self._finish(AuthEvent.UNSUPPORTED)
            return
        previous = self._last_observation
        self._last_observation = result
        if result == "none":
            return
        if result == "authenticated":
            if self._page is None or not authenticated_route(self._page.url().toString()):
                self._finish(AuthEvent.UNSUPPORTED)
                return
            if not self._authenticated:
                self._authenticated = True
                self._helper_timer.stop()
                self._revoke_helper()
                self._dialog.hide()
                self._publish(AuthEvent.AUTHENTICATED)
            return
        if result == "rejected":
            if previous != "rejected":
                self._revoke_helper(keep_request=True)
                self._publish(AuthEvent.REJECTED)
            return
        if result == "expired" and not self._authenticated:
            self._finish(AuthEvent.UNSUPPORTED)
            return
        self._finish({
            "expired": AuthEvent.EXPIRED,
            "unsupported": AuthEvent.UNSUPPORTED,
            "disconnected": AuthEvent.DISCONNECTED,
        }[result])

    def _publish(self, event: AuthEvent) -> None:
        callback = self._callback
        if callback is not None and not self._closed:
            try:
                callback(event)
            except Exception:
                self.close()

    def _finish(self, event: AuthEvent) -> None:
        if self._closed:
            return
        callback = self._callback
        self.close()
        if callback is not None:
            try:
                callback(event)
            except Exception:
                pass

    def _user_cancel(self, result=None) -> None:
        self._finish(AuthEvent.DISCONNECTED)

    def close(self) -> None:
        """Discard the local context without an unverified server logout call."""
        if self._closed:
            return
        self._closed = True
        self._generation += 1
        self._callback = None
        self._authenticated = False
        self._account_callback = None
        self._account_expected = None
        self._account_probe_pending = False
        self._account_request += 1
        self._account_number = None
        self._probe_pending = False
        self._helper_probe_pending = False
        self._helper_request = 0
        self._helper_revision += 1
        self._helper_call("shutdown")
        self._helper_panel = None
        for timer in (self._poll_timer, self._load_timer, self._probe_timer, self._helper_timer,
                      self._account_timer, self._account_deadline):
            timer.stop()
        page, dialog, profile = self._page, self._dialog, self._profile
        self._page = self._view = self._dialog = self._profile = self._interceptor = None
        if page is not None and isValid(page):
            page.triggerAction(QWebEnginePage.WebAction.Stop)
        # A close can originate in a page or dialog signal. Deferred destruction
        # avoids deleting the signal sender while its event is being handled.
        # The view does not own our explicitly parented page; keep the profile
        # until the page's destructor has completed.
        if dialog is not None and isValid(dialog):
            dialog.hide()
            dialog.deleteLater()
        if page is not None and isValid(page):
            if profile is not None and isValid(profile):
                page.destroyed.connect(profile.deleteLater)
            page.deleteLater()
        elif profile is not None and isValid(profile):
            profile.deleteLater()
