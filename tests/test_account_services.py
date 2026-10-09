"""Offline account lifecycle with synthetic browser outcomes and secrets."""

from __future__ import annotations

import ast
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
import inspect
from io import StringIO
import threading
import unittest
from unittest.mock import Mock, patch

from sim_manager.account_models import (
    AccountIssue, AccountPhase, AccountState, AuthEvent, SessionValidity,
)
from sim_manager.message_models import Message, MessageInbox
from sim_manager.services import accounts
from sim_manager.services.accounts import DemoAccountService, DitoAccountService


def inbox(*codes):
    return MessageInbox(tuple(Message(sender="DITO", body=f"{code} is your authentication code.") for code in codes))


class FakeBrowser:
    def __init__(self):
        self.callback = None
        self.open_count = 0
        self.close_count = 0
        self.show_count = 0

    def open(self, callback):
        self.callback = callback
        self.open_count += 1

    def show(self):
        self.show_count += 1

    def close(self):
        self.close_count += 1

    def emit(self, event):
        self.callback(event)


class AccountModelTests(unittest.TestCase):
    def test_default_is_disconnected_with_unknown_validity(self):
        state = AccountState()
        self.assertIs(state.phase, AccountPhase.DISCONNECTED)
        self.assertIs(state.validity, SessionValidity.UNKNOWN)
        self.assertIsNone(state.issue)
        self.assertFalse(state.otp_available)
        self.assertFalse(state.is_demo)

    def test_model_repr_is_opaque_even_for_wrong_private_fields(self):
        state = AccountState(phase={"cookie": "synthetic-cookie"}, issue="synthetic-token", otp_available="123456")
        self.assertEqual(repr(state), "AccountState(<details omitted>)")
        self.assertEqual(str(state), "AccountState(<details omitted>)")

    def test_model_is_immutable_and_carries_no_credentials(self):
        state = AccountState()
        with self.assertRaises(FrozenInstanceError):
            state.phase = AccountPhase.CONNECTED
        self.assertFalse(hasattr(state, "__dict__"))
        for name in ("token", "cookie", "password", "otp", "msisdn", "sms_body"):
            self.assertFalse(hasattr(state, name))


class DitoAccountServiceTests(unittest.TestCase):
    def setUp(self):
        self.browser = FakeBrowser()
        self.factory = Mock(return_value=self.browser)
        self.service = DitoAccountService(self.factory)

    def test_constructing_and_initial_listener_are_inert(self):
        states = []
        self.service.set_listener(states.append)
        self.factory.assert_not_called()
        self.assertEqual(len(states), 1)
        self.assertIs(states[0].phase, AccountPhase.DISCONNECTED)
        self.assertFalse(self.service.is_demo)

    def test_explicit_connect_creates_one_surface_and_starts_connecting(self):
        self.assertTrue(self.service.connect())
        self.assertIs(self.service.state.phase, AccountPhase.CONNECTING)
        self.assertIs(self.service.state.validity, SessionValidity.UNKNOWN)
        self.factory.assert_called_once_with()
        self.assertEqual(self.browser.open_count, 1)

    def test_connect_overlap_and_connected_connect_are_blocked(self):
        self.service.connect()
        self.assertFalse(self.service.connect())
        self.assertEqual(self.browser.show_count, 1)
        self.browser.emit(AuthEvent.AUTHENTICATED)
        self.assertFalse(self.service.connect())
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(self.browser.show_count, 1)

    def test_show_existing_sign_in_error_is_sanitized(self):
        self.service.connect()
        self.browser.show = Mock(side_effect=RuntimeError("synthetic-password"))
        self.assertFalse(self.service.connect())
        self.assertIs(self.service.state.issue, AccountIssue.UNAVAILABLE)
        self.assertEqual(self.browser.close_count, 1)

    def test_success_is_validated_and_clears_candidate(self):
        self.service.connect()
        self.service.offer_otp(inbox("123456"))
        self.browser.emit(AuthEvent.AUTHENTICATED)
        self.assertIs(self.service.state.phase, AccountPhase.CONNECTED)
        self.assertIs(self.service.state.validity, SessionValidity.VALIDATED)
        self.assertIsNone(self.service.state.issue)
        self.assertFalse(self.service.state.otp_available)
        self.assertIsNone(self.service.otp_for_copy())

    def test_rejected_login_remains_open_for_user_retry(self):
        self.service.connect()
        self.service.offer_otp(inbox("123456"))
        self.browser.emit(AuthEvent.REJECTED)
        self.assertIs(self.service.state.phase, AccountPhase.CONNECTING)
        self.assertIs(self.service.state.issue, AccountIssue.REJECTED)
        self.assertFalse(self.service.state.otp_available)
        self.assertEqual(self.browser.close_count, 0)
        self.assertFalse(self.service.connect())
        self.browser.emit(AuthEvent.AUTHENTICATED)
        self.assertIs(self.service.state.phase, AccountPhase.CONNECTED)
        self.assertEqual(self.factory.call_count, 1)

    def test_expiration_closes_session_and_allows_explicit_reconnect(self):
        second = FakeBrowser()
        self.factory.side_effect = [self.browser, second]
        self.service.connect()
        self.browser.emit(AuthEvent.AUTHENTICATED)
        self.browser.emit(AuthEvent.EXPIRED)
        self.assertIs(self.service.state.phase, AccountPhase.EXPIRED)
        self.assertIs(self.service.state.validity, SessionValidity.EXPIRED)
        self.assertIs(self.service.state.issue, AccountIssue.EXPIRED)
        self.assertEqual(self.browser.close_count, 1)
        self.browser.emit(AuthEvent.AUTHENTICATED)
        self.assertIs(self.service.state.phase, AccountPhase.EXPIRED)
        self.assertTrue(self.service.connect())
        second.emit(AuthEvent.AUTHENTICATED)
        self.assertIs(self.service.state.phase, AccountPhase.CONNECTED)

    def test_explicit_disconnect_revokes_session_and_late_callback(self):
        self.service.connect()
        self.browser.emit(AuthEvent.AUTHENTICATED)
        self.service.disconnect()
        self.assertIs(self.service.state.phase, AccountPhase.DISCONNECTED)
        self.assertIs(self.service.state.validity, SessionValidity.UNKNOWN)
        self.assertEqual(self.browser.close_count, 1)
        self.browser.emit(AuthEvent.AUTHENTICATED)
        self.assertIs(self.service.state.phase, AccountPhase.DISCONNECTED)

    def test_cancel_clears_otp_and_ignores_late_success(self):
        self.service.connect()
        self.service.offer_otp(inbox("123456"))
        self.service.cancel()
        self.assertIs(self.service.state.issue, AccountIssue.CANCELLED)
        self.assertIs(self.service.state.phase, AccountPhase.DISCONNECTED)
        self.assertIsNone(self.service.otp_for_copy())
        self.browser.emit(AuthEvent.AUTHENTICATED)
        self.assertIs(self.service.state.phase, AccountPhase.DISCONNECTED)

    def test_browser_closed_by_user_disconnects(self):
        self.service.connect()
        self.browser.emit(AuthEvent.DISCONNECTED)
        self.assertIs(self.service.state.phase, AccountPhase.DISCONNECTED)
        self.assertEqual(self.browser.close_count, 1)

    def test_error_outcomes_close_surface_and_do_not_loop(self):
        for event, issue in ((AuthEvent.UNAVAILABLE, AccountIssue.UNAVAILABLE),
                             (AuthEvent.UNSUPPORTED, AccountIssue.UNSUPPORTED_RESPONSE)):
            with self.subTest(event=event):
                browser = FakeBrowser()
                factory = Mock(return_value=browser)
                service = DitoAccountService(factory)
                service.connect()
                browser.emit(event)
                self.assertIs(service.state.phase, AccountPhase.ERROR)
                self.assertIs(service.state.issue, issue)
                self.assertEqual(browser.close_count, 1)
                self.assertEqual(factory.call_count, 1)

    def test_unknown_raw_event_is_never_exposed(self):
        self.service.connect()
        self.browser.emit({"cookie": "synthetic-cookie", "token": "synthetic-token", "otp": "123456"})
        self.assertIs(self.service.state.issue, AccountIssue.UNSUPPORTED_RESPONSE)
        self.assertNotIn("synthetic", repr(self.service.state))

    def test_missing_factory_fails_closed_without_hidden_io(self):
        with patch("socket.create_connection") as network:
            service = DitoAccountService()
            self.assertFalse(service.connect())
            self.assertIs(service.state.issue, AccountIssue.UNAVAILABLE)
            network.assert_not_called()

    def test_demo_flag_cannot_launch_live_browser(self):
        service = DitoAccountService(self.factory, is_demo=True)
        self.assertFalse(service.connect())
        self.factory.assert_not_called()
        self.assertTrue(service.state.is_demo)

    def test_raw_factory_error_is_sanitized(self):
        service = DitoAccountService(Mock(side_effect=RuntimeError("synthetic-password cookie=synthetic-cookie token=synthetic-token otp=123456")))
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level="DEBUG"):
            self.assertFalse(service.connect())
        self.assertEqual(output.getvalue(), "")
        self.assertIs(service.state.issue, AccountIssue.UNAVAILABLE)
        self.assertEqual(repr(service), "DitoAccountService(<details omitted>)")

    def test_raw_open_error_closes_once_without_private_exception(self):
        self.browser.open = Mock(side_effect=RuntimeError("synthetic-private-token"))
        with self.assertNoLogs(level="DEBUG"):
            self.assertFalse(self.service.connect())
        self.assertIs(self.service.state.issue, AccountIssue.UNAVAILABLE)
        self.assertEqual(self.browser.close_count, 1)
        self.assertIsNone(self.service._browser)

    def test_close_failure_cannot_restore_session_or_escape(self):
        self.service.connect()
        self.browser.close = Mock(side_effect=RuntimeError("synthetic-cookie"))
        self.service.disconnect()
        self.assertIs(self.service.state.phase, AccountPhase.DISCONNECTED)
        self.browser.emit(AuthEvent.AUTHENTICATED)
        self.assertIs(self.service.state.phase, AccountPhase.DISCONNECTED)

    def test_callback_during_close_is_revoked_first(self):
        self.service.connect()
        self.browser.close = lambda: self.browser.emit(AuthEvent.AUTHENTICATED)
        self.service.cancel()
        self.assertIs(self.service.state.phase, AccountPhase.DISCONNECTED)

    def test_listener_can_cancel_before_factory(self):
        self.service.set_listener(lambda state: self.service.cancel() if state.phase is AccountPhase.CONNECTING else None)
        self.assertFalse(self.service.connect())
        self.factory.assert_not_called()
        self.assertIs(self.service.state.issue, AccountIssue.CANCELLED)

    def test_cancel_while_factory_pending_closes_late_browser(self):
        entered, release = threading.Event(), threading.Event()
        def factory():
            entered.set()
            release.wait(1)
            return self.browser
        service = DitoAccountService(factory)
        result = []
        worker = threading.Thread(target=lambda: result.append(service.connect()))
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            service.cancel()
        finally:
            release.set()
            worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result, [False])
        self.assertEqual(self.browser.open_count, 0)
        self.assertEqual(self.browser.close_count, 1)

    def test_new_attempt_ignores_all_old_callbacks(self):
        second = FakeBrowser()
        self.factory.side_effect = [self.browser, second]
        self.service.connect()
        self.service.cancel()
        self.service.connect()
        for event in AuthEvent:
            self.browser.emit(event)
            self.assertIs(self.service.state.phase, AccountPhase.CONNECTING)
        second.emit(AuthEvent.AUTHENTICATED)
        self.assertIs(self.service.state.phase, AccountPhase.CONNECTED)

    def test_listener_detachment_and_errors_do_not_leak(self):
        listener = Mock()
        self.service.set_listener(listener)
        self.service.set_listener(None)
        self.service.connect()
        self.assertEqual(listener.call_count, 1)
        self.service.set_listener(Mock(side_effect=RuntimeError("synthetic-password")))
        with self.assertNoLogs(level="DEBUG"):
            self.browser.emit(AuthEvent.AUTHENTICATED)
        self.assertIs(self.service.state.phase, AccountPhase.CONNECTED)

    def test_shutdown_is_final_idempotent_and_clears_private_references(self):
        listener = Mock()
        self.service.set_listener(listener)
        self.service.connect()
        self.service.offer_otp(inbox("123456"))
        calls = listener.call_count
        self.service.shutdown()
        self.service.shutdown()
        self.assertFalse(self.service.connect())
        self.assertEqual(self.browser.close_count, 1)
        self.assertEqual(listener.call_count, calls)
        self.assertIsNone(self.service._browser)
        self.assertIsNone(self.service._listener)
        self.assertIsNone(self.service._factory)
        self.assertIsNone(self.service.otp_for_copy())
        self.browser.emit(AuthEvent.AUTHENTICATED)
        self.assertIs(self.service.state.phase, AccountPhase.DISCONNECTED)

    def test_otp_is_only_offered_while_connecting(self):
        self.service.offer_otp(inbox("123456"))
        self.assertIsNone(self.service.otp_for_copy())
        self.service.connect()
        self.service.offer_otp(inbox("123456"))
        self.assertTrue(self.service.state.otp_available)
        self.assertEqual(self.service.otp_for_copy(), "123456")
        self.assertEqual(self.browser.show_count, 0)
        self.assertEqual(self.browser.open_count, 1)

    def test_multiple_identical_candidates_are_not_ambiguous(self):
        self.service.connect()
        self.service.offer_otp(inbox("123456", "123456"))
        self.assertEqual(self.service.otp_for_copy(), "123456")

    def test_distinct_candidates_are_ambiguous_without_order_guess(self):
        self.service.connect()
        self.service.offer_otp(inbox("123456"))
        self.service.offer_otp(inbox("123456", "654321"))
        self.assertFalse(self.service.state.otp_available)
        self.assertIsNone(self.service.otp_for_copy())

    def test_explicit_empty_inbox_clears_candidate(self):
        self.service.connect()
        self.service.offer_otp(inbox("123456"))
        self.service.offer_otp(MessageInbox())
        self.assertIsNone(self.service.otp_for_copy())
        self.assertFalse(self.service.state.otp_available)

    def test_unavailable_inbox_does_not_replace_usable_candidate(self):
        self.service.connect()
        self.service.offer_otp(inbox("123456"))
        self.service.offer_otp(MessageInbox(available=False))
        self.assertEqual(self.service.otp_for_copy(), "123456")

    def test_malformed_and_unrelated_messages_do_not_match(self):
        self.service.connect()
        self.service.offer_otp(None)
        self.service.offer_otp(MessageInbox(messages="synthetic-private-body"))
        self.service.offer_otp(MessageInbox((None, Message(sender="Other", body="123456 is your authentication code."))))
        self.assertIsNone(self.service.otp_for_copy())

    def test_service_retains_code_only_and_never_prints_message(self):
        self.service.connect()
        message = Message(identity="synthetic-private-id", sender="DITO", timestamp="Synthetic timestamp", body="123456 is your authentication code. synthetic-private-body")
        with self.assertNoLogs(level="DEBUG"):
            self.service.offer_otp(MessageInbox((message,)))
        self.assertFalse(hasattr(self.service, "_inbox"))
        self.assertFalse(hasattr(self.service, "_messages"))
        self.assertEqual(repr(self.service._otp), "DitoOtpCandidate(<details omitted>)")
        self.assertEqual(repr(self.service.state), "AccountState(<details omitted>)")
        self.assertEqual(repr(self.service), "DitoAccountService(<details omitted>)")

    def test_services_import_no_browser_qt_device_or_storage(self):
        tree = ast.parse(inspect.getsource(accounts))
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
        for name in imports:
            self.assertFalse(any(word in name.lower() for word in ("pyside", "pywebview", "devices", "browser", "sqlite", "keyring")))


class DemoAccountServiceTests(unittest.TestCase):
    def test_synthetic_connect_disconnect_are_explicit_and_labelled(self):
        service = DemoAccountService()
        states = []
        service.set_listener(states.append)
        with patch("socket.create_connection") as network:
            self.assertTrue(service.connect())
            self.assertFalse(service.connect())
            self.assertIs(service.state.phase, AccountPhase.CONNECTED)
            service.disconnect()
            self.assertIs(service.state.phase, AccountPhase.DISCONNECTED)
            network.assert_not_called()
        self.assertTrue(service.is_demo)
        self.assertTrue(all(state.is_demo for state in states))

    def test_demo_never_offers_live_otp(self):
        service = DemoAccountService()
        service.offer_otp(inbox("123456"))
        service.connect()
        service.offer_otp(inbox("123456"))
        self.assertFalse(service.state.otp_available)
        self.assertIsNone(service.otp_for_copy())

    def test_demo_cancel_shutdown_and_listener_detachment(self):
        service = DemoAccountService()
        listener = Mock()
        service.set_listener(listener)
        service.connect()
        service.cancel()
        self.assertIs(service.state.issue, AccountIssue.CANCELLED)
        self.assertIs(service.state.phase, AccountPhase.DISCONNECTED)
        service.set_listener(None)
        calls = listener.call_count
        service.connect()
        service.shutdown()
        service.shutdown()
        self.assertFalse(service.connect())
        self.assertEqual(listener.call_count, calls)

    def test_demo_repr_and_listener_error_are_private(self):
        service = DemoAccountService()
        with self.assertNoLogs(level="DEBUG"):
            service.set_listener(Mock(side_effect=RuntimeError("synthetic-private-token")))
            self.assertTrue(service.connect())
        self.assertEqual(repr(service), "DemoAccountService(<details omitted>)")


if __name__ == "__main__":
    unittest.main()
