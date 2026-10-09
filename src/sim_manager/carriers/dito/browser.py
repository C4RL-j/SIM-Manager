"""Isolated MyDITO authentication surface; private browser state stays here.

The surface observes the official flow. It never supplies credentials, reads
input values, exports cookies or makes a separate authentication request.
"""

from collections.abc import Callable
from os import environ

from PySide6.QtCore import QObject, Qt, QTimer, QUrl
from PySide6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget
from shiboken6 import isValid

from sim_manager.account_models import AuthEvent

from .auth_policy import (
    LOGIN_URL, PROBE_SOURCE, authenticated_route, observer_source,
    request_allowed, trusted_origin,
)


_LOAD_TIMEOUT_MS = 30_000
_PROBE_TIMEOUT_MS = 5_000
_POLL_INTERVAL_MS = 500


class _AuthRequests(QWebEngineUrlRequestInterceptor):
    """A pure allowlist check; no URL, body or header is retained or logged."""

    def interceptRequest(self, info) -> None:
        try:
            method = bytes(info.requestMethod()).decode("ascii", errors="strict")
            allowed = request_allowed(info.requestUrl().toString(), method)
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

    def __init__(self, parent: QObject | None = None) -> None:
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
        self._dialog.resize(1020, 760)
        self._dialog.setMinimumSize(680, 500)
        layout = QVBoxLayout(self._dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        heading = QLabel("Authenticate directly with DITO at https://my.dito.ph")
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setWordWrap(True)
        layout.addWidget(heading)
        note = QLabel("Enter sign-in details and security challenges only on the official page. This session is kept in memory.")
        note.setTextFormat(Qt.TextFormat.PlainText)
        note.setWordWrap(True)
        layout.addWidget(note)
        self._profile = QWebEngineProfile(self)
        if not self._profile.isOffTheRecord() or self._profile.storageName():
            raise RuntimeError("An isolated browser session is required.")
        self._profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self._profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        self._profile.setPersistentPermissionsPolicy(QWebEngineProfile.PersistentPermissionsPolicy.AskEveryTime)
        self._profile.setSpellCheckEnabled(False)
        self._profile.downloadRequested.connect(lambda download: download.cancel())
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
        layout.addWidget(self._view, 1)
        cancel = QPushButton("Cancel sign-in")
        cancel.clicked.connect(self._user_cancel)
        layout.addWidget(cancel)
        self._dialog.finished.connect(self._user_cancel)

    def show(self) -> None:
        if self._closed or self._dialog is None:
            return
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()

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
        self._probe()

    def _load_started(self) -> None:
        if self._closed:
            return
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
            self._finish(AuthEvent.DISCONNECTED)

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
                self._dialog.hide()
                self._publish(AuthEvent.AUTHENTICATED)
            return
        if result == "rejected":
            if previous != "rejected":
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
        self._probe_pending = False
        for timer in (self._poll_timer, self._load_timer, self._probe_timer):
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
