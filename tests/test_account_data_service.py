"""Offline account reads with synthetic values and asynchronous outcomes."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from io import StringIO
import unittest
from unittest.mock import Mock

from sim_manager.account_models import (
    AccountBucket, AccountData, AccountDataIssue, AccountDataResult, AccountIssue,
    AccountPhase, AccountPromo, AccountState, AuthEvent, SessionValidity,
)
from sim_manager.services.accounts import DemoAccountService, DitoAccountService


STAMP = datetime(2026, 1, 1, tzinfo=timezone.utc)


def data(**values):
    return AccountData(updated_at=STAMP, **values)


class ReadBrowser:
    def __init__(self):
        self.auth_callback = None
        self.read_callbacks = []
        self.closed = 0
        self.accept_read = True

    def open(self, callback):
        self.auth_callback = callback

    def show(self):
        pass

    def close(self):
        self.closed += 1

    def refresh_account(self, callback):
        self.read_callbacks.append(callback)
        return self.accept_read

    def authenticate(self):
        self.auth_callback(AuthEvent.AUTHENTICATED)

    def reply(self, result, index=-1):
        self.read_callbacks[index](result)


class AccountDataModelTests(unittest.TestCase):
    def test_retry_delay_is_bounded_rate_limit_metadata_with_opaque_errors(self):
        self.assertEqual(AccountDataResult(issue=AccountDataIssue.RATE_LIMITED, retry_after_seconds=1).retry_after_seconds, 1)
        self.assertEqual(AccountState(data_issue=AccountDataIssue.RATE_LIMITED, retry_after_seconds=3600).retry_after_seconds, 3600)
        for delay in (0, -1, 3601, True, "SYNTHETIC_PRIVATE_RETRY"):
            for constructor in (
                lambda: AccountDataResult(issue=AccountDataIssue.RATE_LIMITED, retry_after_seconds=delay),
                lambda: AccountState(data_issue=AccountDataIssue.RATE_LIMITED, retry_after_seconds=delay),
            ):
                with self.assertRaisesRegex(ValueError, "^Account data is invalid\\.$"):
                    constructor()
        with self.assertRaisesRegex(ValueError, "^Account data is invalid\\.$"):
            AccountDataResult(issue=AccountDataIssue.UNAVAILABLE, retry_after_seconds=30)

    def test_immutable_opaque_optional_values_do_not_invent_totals(self):
        promo = AccountPromo("Synthetic promo", "Synthetic expiry")
        bucket = AccountBucket("Synthetic bucket", "2 GB", "Synthetic expiry")
        value = data(active_promos=(promo,), data_buckets=(bucket,))
        self.assertIsNone(value.load_balance)
        self.assertIsNone(value.data_remaining)
        self.assertEqual(value.data_buckets, (bucket,))
        self.assertEqual(value.source, "official MyDITO")
        for item in (promo, bucket, value, AccountDataResult(data=value), AccountState(data=value)):
            self.assertNotIn("Synthetic", repr(item))
            self.assertFalse(hasattr(item, "__dict__"))
            with self.assertRaises(FrozenInstanceError):
                item.synthetic_private = "synthetic-private"

    def test_invalid_private_values_raise_only_closed_error(self):
        constructors = (
            lambda: AccountPromo("synthetic-private\n"),
            lambda: AccountBucket("Synthetic", "synthetic-private\x00"),
            lambda: data(load_balance={"private": "synthetic-private"}),
            lambda: AccountData(updated_at=datetime(2026, 1, 1)),
            lambda: data(source="synthetic-private-source"),
            lambda: data(active_promos=[AccountPromo("Synthetic")]),
            lambda: data(data_buckets=("synthetic-private-bucket",)),
        )
        for constructor in constructors:
            with self.subTest(constructor=constructor):
                with self.assertRaisesRegex(ValueError, "^Account data is invalid\\.$"):
                    constructor()


class AccountDataServiceTests(unittest.TestCase):
    def setUp(self):
        self.browser = ReadBrowser()
        self.service = DitoAccountService(lambda: self.browser)

    def connected(self):
        self.assertTrue(self.service.connect())
        self.browser.authenticate()

    def test_auto_once_manual_overlap_guard_and_success_replaces_old_data(self):
        self.assertFalse(self.service.refresh_account())
        self.service.connect()
        self.assertFalse(self.service.refresh_account())
        self.browser.authenticate()
        self.assertIs(self.service.state.phase, AccountPhase.CONNECTED)
        self.assertTrue(self.service.state.data_refreshing)
        self.assertEqual(len(self.browser.read_callbacks), 1)
        self.assertFalse(self.service.refresh_account())
        first = data(load_balance="PHP 12", data_remaining="1 GB")
        self.browser.reply(AccountDataResult(data=first))
        self.assertIs(self.service.state.data, first)
        self.assertFalse(self.service.state.data_refreshing)
        self.assertFalse(self.service.state.data_stale)
        self.browser.authenticate()
        self.assertEqual(len(self.browser.read_callbacks), 1)
        self.assertIs(self.service.state.data, first)
        self.assertTrue(self.service.refresh_account())
        second = data(data_remaining="500 MB")
        self.browser.reply(AccountDataResult(data=second))
        self.assertIs(self.service.state.data, second)
        self.assertIsNone(self.service.state.data.load_balance)

    def test_temporary_failure_keeps_original_stamp_and_marks_stale_then_recovers(self):
        self.connected()
        original = data(load_balance="PHP 12")
        self.browser.reply(AccountDataResult(data=original))
        for issue in (AccountDataIssue.UNAVAILABLE, AccountDataIssue.UNSUPPORTED):
            self.assertTrue(self.service.refresh_account())
            self.browser.reply(AccountDataResult(issue=issue))
            self.assertIs(self.service.state.phase, AccountPhase.CONNECTED)
            self.assertIs(self.service.state.data, original)
            self.assertEqual(self.service.state.data.updated_at, STAMP)
            self.assertTrue(self.service.state.data_stale)
            self.assertIs(self.service.state.data_issue, issue)
            self.assertFalse(self.service.state.data_refreshing)
        self.service.refresh_account()
        self.browser.reply(AccountDataResult(data=original))
        self.assertFalse(self.service.state.data_stale)
        self.assertIsNone(self.service.state.data_issue)
        self.assertEqual(self.browser.closed, 0)

    def test_expiry_and_account_mismatch_clear_data_close_and_revoke_both_callbacks(self):
        for issue in (AccountDataIssue.EXPIRED, AccountDataIssue.ACCOUNT_MISMATCH):
            with self.subTest(issue=issue):
                browser = ReadBrowser()
                service = DitoAccountService(lambda: browser)
                service.connect()
                browser.authenticate()
                browser.reply(AccountDataResult(data=data(load_balance="PHP 12")))
                service.refresh_account()
                browser.reply(AccountDataResult(issue=issue))
                self.assertIsNone(service.state.data)
                self.assertFalse(service.state.data_stale)
                self.assertIs(service.state.data_issue, issue)
                self.assertEqual(browser.closed, 1)
                if issue is AccountDataIssue.EXPIRED:
                    self.assertIs(service.state.phase, AccountPhase.EXPIRED)
                    self.assertIs(service.state.validity, SessionValidity.EXPIRED)
                    self.assertIs(service.state.issue, AccountIssue.EXPIRED)
                else:
                    self.assertIs(service.state.phase, AccountPhase.ERROR)
                    self.assertIs(service.state.validity, SessionValidity.UNKNOWN)
                state = service.state
                browser.reply(AccountDataResult(data=data(load_balance="PHP 99")))
                browser.authenticate()
                self.assertIs(service.state, state)
                self.assertFalse(service.refresh_account())

    def test_disconnect_reconnect_shutdown_discard_old_request_and_account(self):
        self.connected()
        self.browser.reply(AccountDataResult(data=data(load_balance="PHP 12")))
        self.service.refresh_account()
        self.service.disconnect()
        self.assertIsNone(self.service.state.data)
        self.assertFalse(self.service.state.data_refreshing)
        second = ReadBrowser()
        self.service._factory = lambda: second
        self.assertTrue(self.service.connect())
        second.authenticate()
        current = self.service.state
        self.browser.reply(AccountDataResult(data=data(load_balance="PHP 99")))
        self.assertIs(self.service.state, current)
        second.reply(AccountDataResult(data=data(load_balance="PHP 20")))
        self.service.refresh_account()
        self.service.shutdown()
        second.reply(AccountDataResult(data=data(load_balance="PHP 99")))
        self.assertIsNone(self.service.state.data)
        self.assertFalse(self.service.refresh_account())
        self.assertEqual(second.closed, 1)

    def test_old_and_duplicate_result_cannot_replace_current_request(self):
        self.connected()
        first = data(load_balance="PHP 12")
        self.browser.reply(AccountDataResult(data=first))
        self.browser.reply(AccountDataResult(data=data(load_balance="PHP 99")))
        self.assertIs(self.service.state.data, first)
        self.assertTrue(self.service.refresh_account())
        pending = self.service.state
        self.browser.reply(AccountDataResult(issue=AccountDataIssue.EXPIRED), index=0)
        self.assertIs(self.service.state, pending)
        second = data(load_balance="PHP 20")
        self.browser.reply(AccountDataResult(data=second))
        self.assertIs(self.service.state.data, second)
        self.assertEqual(self.browser.closed, 0)

    def test_reentrant_listener_cancel_before_read_and_during_close_is_safe(self):
        self.service.set_listener(
            lambda state: self.service.cancel() if state.data_refreshing else None,
        )
        self.connected()
        self.assertEqual(self.browser.read_callbacks, [])
        self.assertIs(self.service.state.phase, AccountPhase.DISCONNECTED)
        self.assertIsNone(self.service.state.data)
        self.assertEqual(self.browser.closed, 1)

        other = ReadBrowser()
        service = DitoAccountService(lambda: other)
        service.connect()
        other.authenticate()
        other.close = lambda: other.reply(AccountDataResult(data=data(load_balance="PHP 99")))
        service.disconnect()
        self.assertIsNone(service.state.data)
        self.assertIs(service.state.phase, AccountPhase.DISCONNECTED)

    def test_refusal_raw_exceptions_malformed_results_and_listener_errors_never_leak(self):
        raw_private = "synthetic-phone otp=123456 cookie=synthetic token=synthetic raw-response"
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level="DEBUG"):
            self.connected()
            for result in (
                {"response": raw_private},
                AccountDataResult(),
                AccountDataResult(data=data(load_balance="PHP 12"), issue=AccountDataIssue.UNAVAILABLE),
                AccountDataResult(data=raw_private),
                AccountDataResult(issue=raw_private),
            ):
                if not self.service.state.data_refreshing:
                    self.assertTrue(self.service.refresh_account())
                self.browser.reply(result)
                self.assertIs(self.service.state.data_issue, AccountDataIssue.UNSUPPORTED)
                self.assertIsNone(self.service.state.data)
            self.browser.accept_read = False
            self.assertFalse(self.service.refresh_account())
            self.assertIs(self.service.state.data_issue, AccountDataIssue.UNAVAILABLE)
            self.browser.refresh_account = Mock(side_effect=RuntimeError(raw_private))
            self.assertFalse(self.service.refresh_account())
            self.assertFalse(self.service.state.data_refreshing)
            self.service.set_listener(Mock(side_effect=RuntimeError(raw_private)))
            self.assertFalse(self.service.refresh_account())
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn(raw_private, repr(self.service.state))
        self.assertEqual(self.browser.closed, 0)

    def test_synchronous_success_and_demo_remain_network_independent(self):
        value = data(load_balance="PHP 12")
        def immediate(callback):
            callback(AccountDataResult(data=value))
            return True
        self.browser.refresh_account = immediate
        self.connected()
        self.assertIs(self.service.state.data, value)
        self.assertFalse(self.service.state.data_refreshing)
        demo = DemoAccountService()
        demo.connect()
        self.assertFalse(demo.refresh_account())
        self.assertIsNone(demo.state.data)

    def test_rate_limit_preserves_values_and_service_enforces_cooldown_without_scheduler(self):
        now = [100.0]
        browser = ReadBrowser()
        service = DitoAccountService(lambda: browser, clock=lambda: now[0])
        service.connect()
        browser.authenticate()
        original = data(load_balance="PHP 12")
        browser.reply(AccountDataResult(data=original))
        service.refresh_account()
        browser.reply(AccountDataResult(issue=AccountDataIssue.RATE_LIMITED, retry_after_seconds=120))
        self.assertIs(service.state.phase, AccountPhase.CONNECTED)
        self.assertIs(service.state.data, original)
        self.assertTrue(service.state.data_stale)
        self.assertEqual(service.state.retry_after_seconds, 120)
        self.assertFalse(service.refresh_account())
        self.assertEqual(len(browser.read_callbacks), 2)
        now[0] += 119
        self.assertFalse(service.refresh_account())
        self.assertEqual(service.state.retry_after_seconds, 1)
        now[0] += 1
        self.assertTrue(service.refresh_account())
        self.assertEqual(len(browser.read_callbacks), 3)
        self.assertIsNone(service.state.retry_after_seconds)
        browser.reply(AccountDataResult(data=original))
        self.assertFalse(service.state.data_stale)
        self.assertIsNone(service.state.data_issue)

    def test_rate_limit_without_hint_has_bounded_fallback_and_login_read_cannot_bypass_it(self):
        now = [100.0]
        browsers = [ReadBrowser(), ReadBrowser()]
        service = DitoAccountService(lambda: browsers.pop(0), clock=lambda: now[0])
        first = browsers[0]
        service.connect()
        first.authenticate()
        first.reply(AccountDataResult(issue=AccountDataIssue.RATE_LIMITED))
        service.disconnect()
        second = browsers[0]
        service.connect()
        second.authenticate()
        self.assertIs(service.state.data_issue, AccountDataIssue.RATE_LIMITED)
        self.assertEqual(service.state.retry_after_seconds, 60)
        self.assertEqual(second.read_callbacks, [])
        now[0] += 60
        self.assertTrue(service.refresh_account())
        self.assertEqual(len(second.read_callbacks), 1)


if __name__ == "__main__":
    unittest.main()
