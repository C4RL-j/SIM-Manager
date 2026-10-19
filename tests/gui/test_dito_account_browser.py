"""Offline account-data reads through the isolated synthetic browser boundary."""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
import io
import json
import os
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QCoreApplication, QEvent, QUrl
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineScript
from PySide6.QtWidgets import QApplication

from sim_manager.account_models import AccountDataIssue, AuthEvent
from sim_manager.carriers.dito import browser

from test_dito_browser import FakePage, FakeProfile, FakeView


class AccountPage(FakePage):
    def __init__(self, profile, parent):
        super().__init__(profile, parent)
        self.account_start_result = True
        self.account_result = None
        self.account_pending = False
        self.account_callbacks = []
        self.account_calls = []

    def runJavaScript(self, source, *arguments):
        if "__simManagerDitoAccountData" not in source:
            return super().runJavaScript(source, *arguments)
        if len(arguments) == 1 and not callable(arguments[0]):
            self.account_calls.append((source, arguments[0]))
            return
        if len(arguments) == 1:
            world, callback = QWebEngineScript.ScriptWorldId.MainWorld, arguments[0]
        elif len(arguments) == 2:
            world, callback = arguments
        else:
            raise TypeError("Unsupported synthetic account JavaScript call")
        self.account_calls.append((source, world))
        if self.account_pending:
            self.account_callbacks.append(callback)
        else:
            callback(self.account_start_result if ".start(" in source else self.account_result)


def result(request, state="ok", **values):
    fields = {
        "load_balance": None, "data_remaining": None, "active_promos": [],
        "expiry": None, "sms_allowance": None, "call_allowance": None,
        "data_buckets": [],
    }
    fields.update(values)
    return json.dumps({"request": request, "state": state,
                       "data": fields if state == "ok" else None})


class RequestInfo:
    def __init__(self, url, method):
        self.url = url
        self.method = method
        self.blocked = None

    def requestUrl(self):
        return QUrl(self.url)

    def requestMethod(self):
        return self.method.encode("ascii")

    def block(self, blocked):
        self.blocked = blocked


class DitoAccountBrowserTests(unittest.TestCase):
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
        self.guards.enter_context(patch.object(browser, "_DitoPage", AccountPage))
        self.guards.enter_context(patch.object(browser, "QWebEngineView", FakeView))
        self.number = "09920000001"
        self.events = []
        self.results = []
        self.surface = browser.DitoBrowserSurface(account_number=lambda: self.number)
        self.guards.enter_context(patch.object(self.surface, "show"))
        self.addCleanup(self.clean_surface)

    def flush_deletes(self):
        for _ in range(3):
            self.application.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def clean_surface(self):
        self.surface.close()
        self.flush_deletes()
        self.surface.deleteLater()
        self.flush_deletes()

    def opened(self):
        self.surface.open(self.events.append)
        return self.surface._page, self.surface._profile

    def connected(self):
        page, profile = self.opened()
        page.loadFinished.emit(True)
        page._url = QUrl("https://my.dito.ph/pto/home")
        page.result = "authenticated"
        self.surface._probe()
        self.assertEqual(self.events, [AuthEvent.AUTHENTICATED])
        return page, profile

    def test_reader_is_opt_in_main_frame_and_preserves_isolated_auth_flow(self):
        self.assertFalse(self.surface.refresh_account(self.results.append))
        page, profile = self.opened()
        scripts = page.scripts().items
        self.assertEqual(scripts[0].name(), "SIM Manager authentication observer")
        readers = [script for script in scripts if "__simManagerDitoAccountData" in script.sourceCode()]
        self.assertEqual(len(readers), 1)
        reader = readers[0]
        self.assertEqual(reader.injectionPoint(), QWebEngineScript.InjectionPoint.DocumentCreation)
        self.assertEqual(reader.worldId(), QWebEngineScript.ScriptWorldId.MainWorld)
        self.assertFalse(reader.runsOnSubFrames())
        self.assertEqual(profile.cookies, QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self.assertEqual(profile.cache, QWebEngineProfile.HttpCacheType.MemoryHttpCache)
        self.assertTrue(profile.isOffTheRecord())
        self.assertEqual(profile.storageName(), "")
        self.assertEqual(page.loaded_url, QUrl("https://my.dito.ph/"))
        self.assertEqual(self.surface._view.zoomFactor(), 0.88)
        self.assertFalse(self.surface.refresh_account(self.results.append))
        self.assertEqual(page.account_calls, [])

        plain = browser.DitoBrowserSurface()
        self.addCleanup(plain.close)
        with patch.object(plain, "show"):
            plain.open(lambda event: None)
        self.assertFalse(any("__simManagerDitoAccountData" in script.sourceCode()
                             for script in plain._page.scripts().items))
        for surface, allowed in ((self.surface, True), (plain, False)):
            info = RequestInfo("https://my.dito.ph/ecare/webs/balance/balInfo", "POST")
            surface._interceptor.interceptRequest(info)
            self.assertEqual(info.blocked, not allowed)
            forbidden = RequestInfo("https://my.dito.ph/layouts__BaseLayout.0123abcd.async.js", "GET")
            surface._interceptor.interceptRequest(forbidden)
            self.assertTrue(forbidden.blocked)
        plain.close()
        self.flush_deletes()
        plain.deleteLater()
        self.flush_deletes()

    def test_start_pending_success_keeps_exact_verified_fields_and_blocks_overlap(self):
        page, _ = self.connected()
        page.account_result = result(1, "pending")
        self.assertTrue(self.surface.refresh_account(self.results.append))
        self.assertTrue(self.surface._account_timer.isActive())
        self.assertTrue(self.surface._account_deadline.isActive())
        self.assertEqual(self.surface._account_deadline.interval(), 30_000)
        self.assertFalse(self.surface.refresh_account(self.results.append))
        self.assertEqual(self.results, [])
        page.account_result = result(
            1, load_balance="PHP 12", data_remaining="2 GB",
            active_promos=[{"name": "Synthetic promo", "expiry": None}],
            data_buckets=[
                {"name": "Synthetic data", "remaining": "1 GB", "expiry": "Synthetic expiry"},
                {"name": "Synthetic bonus", "remaining": "500 MB", "expiry": None},
            ], sms_allowance="20 SMS", call_allowance="10 minutes",
        )
        self.surface._probe_account()
        self.assertEqual(len(self.results), 1)
        snapshot = self.results[0].data
        self.assertIsNone(self.results[0].issue)
        self.assertEqual(snapshot.load_balance, "PHP 12")
        self.assertEqual(snapshot.data_remaining, "2 GB")
        self.assertEqual(snapshot.active_promos[0].name, "Synthetic promo")
        self.assertIsNone(snapshot.expiry)
        self.assertEqual([item.remaining for item in snapshot.data_buckets], ["1 GB", "500 MB"])
        self.assertEqual(snapshot.sms_allowance, "20 SMS")
        self.assertEqual(snapshot.call_allowance, "10 minutes")
        self.assertIsNotNone(snapshot.updated_at.tzinfo)
        self.assertEqual(snapshot.source, "official MyDITO")
        self.assertFalse(self.surface._account_timer.isActive())
        self.assertFalse(self.surface._account_deadline.isActive())
        self.assertTrue(all(world == QWebEngineScript.ScriptWorldId.MainWorld
                            for _, world in page.account_calls))
        self.assertTrue(any(".stop()" in source for source, _ in page.account_calls))
        self.assertEqual(self.events, [AuthEvent.AUTHENTICATED])
        self.assertFalse(self.surface._closed)

    def test_failed_start_invalid_payload_and_closed_outcomes_preserve_authentication(self):
        page, _ = self.connected()
        page.account_start_result = False
        self.assertTrue(self.surface.refresh_account(self.results.append))
        self.assertIs(self.results[-1].issue, AccountDataIssue.UNSUPPORTED)
        page.account_start_result = True
        for value, expected in (
            ("synthetic-private-raw-response", AccountDataIssue.UNSUPPORTED),
            (result(99, "ok"), AccountDataIssue.UNSUPPORTED),
            (result(4, "unsupported"), AccountDataIssue.UNSUPPORTED),
            (result(5, "unavailable"), AccountDataIssue.UNAVAILABLE),
            (result(6, "account_mismatch"), AccountDataIssue.ACCOUNT_MISMATCH),
        ):
            page.account_result = value
            self.assertTrue(self.surface.refresh_account(self.results.append))
            self.assertIs(self.results[-1].issue, expected)
            self.assertIsNone(self.results[-1].data)
            self.assertFalse(self.surface._account_timer.isActive())
        self.assertEqual(self.events, [AuthEvent.AUTHENTICATED])
        self.assertTrue(self.surface._authenticated)

    def test_timeout_new_request_and_close_ignore_late_callbacks(self):
        page, _ = self.connected()
        page.account_pending = True
        self.assertTrue(self.surface.refresh_account(self.results.append))
        first_start = page.account_callbacks.pop()
        self.surface._account_deadline.timeout.emit()
        self.assertEqual(len(self.results), 1)
        self.assertIs(self.results[-1].issue, AccountDataIssue.UNAVAILABLE)
        self.assertTrue(self.surface.refresh_account(self.results.append))
        second_start = page.account_callbacks.pop()
        call_count = len(page.account_calls)
        first_start(True)
        self.assertEqual(len(page.account_calls), call_count)
        second_start(True)
        second_poll = page.account_callbacks.pop()
        self.surface.close()
        second_poll(result(2, load_balance="PHP 99"))
        self.assertEqual(len(self.results), 1)
        self.assertIsNone(self.surface._account_callback)
        self.assertIsNone(self.surface._account_number)
        self.assertFalse(self.surface._account_timer.isActive())
        self.assertFalse(self.surface._account_deadline.isActive())
        self.assertEqual(self.events, [AuthEvent.AUTHENTICATED])

    def test_sim_change_and_route_change_revoke_pending_results(self):
        page, _ = self.connected()
        page.account_pending = True
        self.surface.refresh_account(self.results.append)
        page.account_callbacks.pop()(True)
        pending = page.account_callbacks.pop()
        self.number = "09920000002"
        pending(result(1, load_balance="PHP 99"))
        self.assertEqual(len(self.results), 1)
        self.assertIs(self.results[0].issue, AccountDataIssue.ACCOUNT_MISMATCH)
        self.assertIsNone(self.results[0].data)
        self.number = "09920000001"
        self.surface.refresh_account(self.results.append)
        page.account_callbacks.pop()(True)
        pending = page.account_callbacks.pop()
        page._url = QUrl("https://my.dito.ph/")
        pending(result(2, load_balance="PHP 99"))
        self.assertIs(self.results[-1].issue, AccountDataIssue.EXPIRED)
        self.assertIsNone(self.results[-1].data)

    def test_private_exceptions_callbacks_and_missing_reader_never_escape(self):
        page, _ = self.connected()
        private = "synthetic-phone OTP=123456 cookie=synthetic token=synthetic raw-response"
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level="DEBUG"):
            self.number = None
            self.assertTrue(self.surface.refresh_account(self.results.append))
            self.assertIs(self.results[-1].issue, AccountDataIssue.ACCOUNT_MISMATCH)
            self.assertTrue(self.surface.refresh_account(
                lambda value: (_ for _ in ()).throw(RuntimeError(private)),
            ))
            self.number = "09920000001"
            with patch.object(page, "runJavaScript", side_effect=RuntimeError(private)):
                self.assertTrue(self.surface.refresh_account(self.results.append))
            self.assertIs(self.results[-1].issue, AccountDataIssue.UNAVAILABLE)
            page.account_start_result = False
            self.assertTrue(self.surface.refresh_account(self.results.append))
            self.assertIs(self.results[-1].issue, AccountDataIssue.UNSUPPORTED)
            self.assertNotIn(private, repr(self.results[-1]))
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(self.events, [AuthEvent.AUTHENTICATED])
        self.assertFalse(self.surface._closed)


if __name__ == "__main__":
    unittest.main()
