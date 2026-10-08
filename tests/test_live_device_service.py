"""Offline authentication orchestration and session-expiry boundaries."""

from dataclasses import asdict
from threading import Event
import traceback
import unittest
from unittest.mock import patch

from sim_manager.devices.d2.errors import (
    D2AuthenticationRejected, D2AuthenticationRequired, D2Cancelled,
    D2ConnectionError, D2MalformedAuthentication, D2Timeout, D2Unreachable,
)
from sim_manager.devices.d2 import status as d2_status
from sim_manager.devices.d2.status import D2StatusClient, ENDPOINTS
from sim_manager.models import DeviceState, IssueCode
from sim_manager.services.device import (
    AuthenticationError, AuthenticationFailure, LiveDeviceService, RefreshCancelled,
)
from sim_manager.services.presentation import present_device


PRIVATE = "SYNTHETIC_SECRET_NOT_REAL"
USERNAME = "synthetic-admin"


class FakeSession:
    origin = "https://192.168.1.1"

    def __init__(self, *, login_error=None, responses=()):
        self.login_error = login_error
        self.responses = list(responses)
        self.authenticated = False
        self.login_calls = 0
        self.read_calls = []
        self.invalidations = 0
        self.closed = False

    def authenticate(self, password, *, username, timeout, stop_event):
        self.login_calls += 1
        self.authenticated = False
        if self.login_error is not None:
            raise self.login_error
        self.authenticated = True

    def read_json(self, path, **kwargs):
        if not self.authenticated:
            raise D2AuthenticationRequired()
        self.read_calls.append(path)
        item = self.responses.pop(0) if self.responses else d2_status.StatusResponse(200, {"code": 200, "data": {}})
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item()
        return item

    def invalidate(self):
        self.authenticated = False
        self.invalidations += 1

    def close(self):
        self.closed = True
        self.authenticated = False


class LiveAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.guard = patch("socket.socket", side_effect=AssertionError("Offline only"))
        self.guard.start()
        self.addCleanup(self.guard.stop)

    def test_successful_login_automatically_reads_all_seven_getters(self):
        session = FakeSession()
        service = LiveDeviceService(session=session)
        state = service.authenticate(PRIVATE, username=USERNAME)
        self.assertEqual(session.login_calls, 1)
        self.assertEqual(session.read_calls, list(ENDPOINTS.values()))
        self.assertFalse(state.partial)
        self.assertEqual(present_device(state).router_status, "Status available")
        self.assertEqual(present_device(state).carrier, "Unknown")
        self.assertEqual(service.router_address, session.origin)
        self.assertNotIn(PRIVATE, repr(service))

    def test_all_login_errors_are_closed_safe_outcomes_without_raw_chains(self):
        cases = (
            (D2AuthenticationRejected(), AuthenticationFailure.REJECTED),
            (D2MalformedAuthentication(), AuthenticationFailure.MALFORMED),
            (D2Timeout(), AuthenticationFailure.TIMEOUT),
            (D2Unreachable(), AuthenticationFailure.UNREACHABLE),
            (D2ConnectionError(), AuthenticationFailure.CONNECTION),
            (D2Cancelled(), AuthenticationFailure.CANCELLED),
            (RuntimeError(PRIVATE), AuthenticationFailure.MALFORMED),
        )
        for original, expected in cases:
            with self.subTest(expected=expected, kind=type(original).__name__):
                session = FakeSession(login_error=original)
                service = LiveDeviceService(session=session)
                try:
                    service.authenticate(PRIVATE, username=USERNAME)
                except AuthenticationError as error:
                    self.assertIs(error.code, expected)
                    self.assertNotIn(PRIVATE, str(error))
                    self.assertNotIn(PRIVATE, repr(error))
                    self.assertNotIn(PRIVATE, "".join(traceback.format_exception(error)))
                    self.assertIsNone(error.__cause__)
                else:
                    self.fail("Expected safe authentication failure")
                self.assertEqual(session.login_calls, 1)
                self.assertEqual(session.read_calls, [])

    def test_cancelled_before_login_never_submits_credentials(self):
        session = FakeSession()
        stop = Event()
        stop.set()
        with self.assertRaises(AuthenticationError) as result:
            LiveDeviceService(session=session).authenticate(PRIVATE, username=USERNAME, stop_event=stop)
        self.assertIs(result.exception.code, AuthenticationFailure.CANCELLED)
        self.assertEqual(session.login_calls, 0)

    def test_empty_or_nontext_credentials_fail_without_network_or_echo(self):
        session = FakeSession()
        for password in ("", None, {PRIVATE: PRIVATE}):
            with self.subTest(kind=type(password).__name__):
                with self.assertRaises(AuthenticationError) as result:
                    LiveDeviceService(session=session).authenticate(password, username=USERNAME)
                self.assertIs(result.exception.code, AuthenticationFailure.MALFORMED)
                self.assertNotIn(PRIVATE, repr(result.exception))
        self.assertEqual(session.login_calls, 0)

    def test_missing_or_nontext_username_fails_without_login_attempt(self):
        session = FakeSession()
        for username in ("", "   ", None, {PRIVATE: PRIVATE}):
            with self.subTest(kind=type(username).__name__):
                with self.assertRaises(AuthenticationError) as result:
                    LiveDeviceService(session=session).authenticate(PRIVATE, username=username)
                self.assertIs(result.exception.code, AuthenticationFailure.MALFORMED)
                self.assertNotIn(PRIVATE, repr(result.exception))
        self.assertEqual(session.login_calls, 0)

    def test_session_expiry_stops_cycle_invalidates_and_allows_explicit_relogin(self):
        session = FakeSession(responses=[d2_status.StatusResponse(401, {"code": 401, "msg": PRIVATE})])
        service = LiveDeviceService(session=session)
        expired = service.authenticate(PRIVATE, username=USERNAME)
        self.assertEqual(session.read_calls, [next(iter(ENDPOINTS.values()))])
        self.assertFalse(session.authenticated)
        self.assertEqual(session.invalidations, 1)
        self.assertEqual({issue.code for issue in expired.errors}, {IssueCode.AUTHENTICATION_REQUIRED})
        self.assertEqual(present_device(expired).notice, "Authentication required")
        # Refresh never retries authentication itself or proceeds to protected GETs.
        service.get_device_state()
        self.assertEqual(session.login_calls, 1)
        self.assertEqual(len(session.read_calls), 1)
        state = service.authenticate(PRIVATE, username=USERNAME)
        self.assertEqual(session.login_calls, 2)
        self.assertFalse(state.partial)

    def test_body_authentication_failure_also_invalidates_session(self):
        session = FakeSession(responses=[d2_status.StatusResponse(200, {"code": 403, "msg": PRIVATE})])
        state = LiveDeviceService(session=session).authenticate(PRIVATE, username=USERNAME)
        self.assertEqual(len(session.read_calls), 1)
        self.assertFalse(session.authenticated)
        self.assertEqual(present_device(state).notice, "Authentication required")

    def test_permission_failure_invalidates_injected_session(self):
        session = FakeSession(responses=[D2AuthenticationRequired()])
        state = LiveDeviceService(session=session).authenticate(PRIVATE, username=USERNAME)
        self.assertFalse(session.authenticated)
        self.assertEqual(len(session.read_calls), 1)
        self.assertEqual(present_device(state).notice, "Authentication required")

    def test_partial_status_failure_keeps_good_values_after_authentication(self):
        success = d2_status.StatusResponse(200, {"code": 200, "data": {"Status": "Connected", "Band": "1/28", "RSRP": "-91"}})
        session = FakeSession(responses=[D2ConnectionError(), success])
        state = LiveDeviceService(session=session).authenticate(PRIVATE, username=USERNAME)
        self.assertTrue(session.authenticated)
        self.assertEqual(len(session.read_calls), 7)
        self.assertTrue(state.partial)
        self.assertEqual(state.radio.bands, (1, 28))
        view = present_device(state)
        self.assertEqual(view.rsrp, "-91")
        self.assertEqual(view.router_status, "Partial data")
        self.assertEqual(view.notice, "Router connection problem")
        self.assertNotIn(PRIVATE, repr(asdict(view)))

    def test_status_transport_failures_distinguish_connection_from_unreachable(self):
        for error, code, notice in (
            (D2Unreachable(), IssueCode.UNREACHABLE, "Router unreachable"),
            (D2ConnectionError(), IssueCode.CONNECTION_ERROR, "Router connection problem"),
        ):
            with self.subTest(code=code):
                session = FakeSession(responses=[error] * 7)
                state = LiveDeviceService(session=session).authenticate(PRIVATE, username=USERNAME)
                self.assertEqual({issue.code for issue in state.errors}, {code})
                self.assertEqual(present_device(state).notice, notice)

    def test_cancellation_exception_stops_status_cycle_without_further_reads(self):
        session = FakeSession(responses=[D2Cancelled()])
        session.authenticated = True
        state = D2StatusClient(session).get_device_state()
        self.assertEqual(len(session.read_calls), 1)
        self.assertEqual({issue.code for issue in state.errors}, {IssueCode.CANCELLED})

    def test_expiry_invalidates_even_when_cancellation_wins_display_priority(self):
        for exception_failure in (True, False):
            with self.subTest(exception_failure=exception_failure):
                stop = Event()

                def expired():
                    stop.set()
                    if exception_failure:
                        raise D2AuthenticationRequired()
                    return d2_status.StatusResponse(401, {"code": 401})

                session = FakeSession(responses=[expired])
                session.authenticated = True
                state = D2StatusClient(session).get_device_state(stop_event=stop)
                self.assertFalse(session.authenticated)
                self.assertEqual(session.invalidations, 1)
                self.assertEqual(len(session.read_calls), 1)
                self.assertEqual({issue.code for issue in state.errors}, {IssueCode.CANCELLED})

    def test_unknown_authentication_error_code_cannot_echo_input(self):
        error = AuthenticationError(PRIVATE)
        self.assertIs(error.code, AuthenticationFailure.MALFORMED)
        self.assertNotIn(PRIVATE, repr(error))

    def test_service_close_discards_owned_session_without_hardware_logout(self):
        session = FakeSession()
        service = LiveDeviceService(session=session)
        service.authenticate(PRIVATE, username=USERNAME)
        service.close()
        self.assertTrue(session.closed)
        self.assertFalse(session.authenticated)


if __name__ == "__main__":
    unittest.main()
