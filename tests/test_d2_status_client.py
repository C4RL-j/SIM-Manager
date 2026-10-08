"""Offline tests for the authenticated, read-only D2 snapshot boundary.

All readers, clocks and events are synthetic. The Task 004 fixture preserves
user-collected sanitized summaries; concealed raw fixture values are rebuilt
with explicitly synthetic placeholders, never inferred hardware observations.
"""

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, asdict
from datetime import datetime, timezone
import importlib
import io
import json
import logging
from pathlib import Path
import threading
import unittest
from unittest.mock import patch


with patch("socket.socket", side_effect=AssertionError("Real sockets forbidden")):
    with patch("socket.create_connection", side_effect=AssertionError("Real connections forbidden")):
        from sim_manager.devices.d2 import status
        from sim_manager.models import (
            Availability, CarrierEvidence, ConnectionMode, ConnectionState,
            DeviceIssue, DeviceState, IssueCode, NetworkState, PinState,
            RadioState, Readiness, SimState, WanState,
        )


EXPECTED_ENDPOINTS = {
    "wireless": "/web/v1/dashboard/wirelessinfo",
    "internet": "/web/v1/dashboard/internetinfo",
    "wan": "/web/v1/dashboard/waninfo",
    "device": "/web/v1/dashboard/deviceinfo",
    "wanStatus": "/web/v1/status/wanstatus",
    "sim": "/web/v1/setting/network/pinmanagement/simcardinfo",
    "deviceDetails": "/web/v1/setting/deviceinfo",
}
SOURCES = tuple(EXPECTED_ENDPOINTS)
PATHS = tuple(EXPECTED_ENDPOINTS.values())
PRIVATE = "SYNTHETIC_PRIVATE_TOKEN"
OBSERVED_AT = datetime(2026, 10, 8, 4, 5, 6, tzinfo=timezone.utc)
FIXTURE = Path(__file__).parent / "fixtures" / "d2" / "authenticated-report.json"


def successful_response(data=None):
    return status.StatusResponse(200, {"code": 200, "data": {} if data is None else data})


def reconstructed_responses():
    """Rebuild shapes, using synthetic strings for every concealed raw value."""
    report = json.loads(FIXTURE.read_text(encoding="utf-8"))["report"]
    responses = []
    for request in report["requests"]:
        payload = {"code": request["summary"]["code"], "data": {}}
        for field_path, descriptor in request["summary"]["fields"].items():
            cursor = payload
            components = field_path.split(".")
            for component in components[:-1]:
                cursor = cursor.setdefault(component, {})
            value = descriptor["value"]
            cursor[components[-1]] = PRIVATE if value in ("masked", "omitted") else value
        # Future/private fields are not permitted to escape the model boundary.
        payload["data"]["UnknownFutureField"] = {"Authorization": PRIVATE}
        responses.append(status.StatusResponse(request["http_status"], payload))
    return responses


class FakeClock:
    def __init__(self, value=100.0):
        self.value = value
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.value


class FakeNow:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return OBSERVED_AT


class FakeSession:
    """Record calls and replay values, exceptions or deterministic callbacks."""

    def __init__(self, actions=()):
        self.actions = list(actions)
        self.calls = []

    def __repr__(self):
        return PRIVATE

    def read_json(self, path, *, deadline, stop_event, max_bytes):
        self.calls.append((path, deadline, stop_event, max_bytes))
        index = len(self.calls) - 1
        action = self.actions[index] if index < len(self.actions) else successful_response()
        if isinstance(action, BaseException):
            raise action
        if callable(action):
            return action()
        return action


class OfflineStatusCase(unittest.TestCase):
    def setUp(self):
        self.guards = ExitStack()
        self.addCleanup(self.guards.close)
        for target in ("socket.socket", "socket.create_connection", "subprocess.Popen", "webbrowser.open"):
            self.guards.enter_context(patch(target, side_effect=AssertionError("External I/O forbidden")))
        self.clock = FakeClock()
        self.now = FakeNow()

    def client(self, session=None):
        return status.D2StatusClient(session, clock=self.clock, now=self.now)

    def assert_issues(self, snapshot, sources, code):
        self.assertEqual(tuple(issue.source for issue in snapshot.errors), tuple(sources))
        self.assertEqual(tuple(issue.code for issue in snapshot.errors), (code,) * len(sources))

    def assert_sources(self, snapshot, sources):
        self.assertEqual(snapshot.successful_sources, tuple(sources))

    def assert_private(self, value):
        self.assertNotIn(PRIVATE, repr(value))
        self.assertNotIn(PRIVATE, str(value))


class StatusBoundaryTests(OfflineStatusCase):
    def test_import_and_default_client_are_inert(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            importlib.reload(status)
            client = self.client()
            snapshot = client.get_device_state()
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")
        self.assert_issues(snapshot, SOURCES, IssueCode.AUTHENTICATION_REQUIRED)
        self.assert_sources(snapshot, ())
        self.assertTrue(snapshot.partial)

    def test_endpoint_registry_is_the_exact_ordered_reviewed_set(self):
        self.assertEqual(dict(status.ENDPOINTS), EXPECTED_ENDPOINTS)
        self.assertEqual(tuple(status.ENDPOINTS), SOURCES)

    def test_endpoint_registry_cannot_be_mutated_into_a_write_request(self):
        with self.assertRaises(TypeError):
            status.ENDPOINTS["wireless"] = "/synthetic/unreviewed"
        self.assertEqual(dict(status.ENDPOINTS), EXPECTED_ENDPOINTS)

    def test_fixed_read_paths_share_one_deadline_event_and_byte_cap(self):
        session, stop = FakeSession(), threading.Event()
        snapshot = self.client(session).get_device_state(timeout=12.5, stop_event=stop)
        self.assertEqual(session.calls, [(path, 112.5, stop, 256 * 1024) for path in PATHS])
        self.assert_sources(snapshot, SOURCES)
        self.assertEqual(snapshot.errors, ())
        self.assertFalse(snapshot.partial)

    def test_snapshot_timestamp_is_requested_once_and_preserved(self):
        snapshot = self.client(FakeSession()).get_device_state()
        self.assertEqual(self.now.calls, 1)
        self.assertIs(snapshot.observed_at, OBSERVED_AT)
        self.assertEqual(snapshot.source, "device:d2")

    def test_default_unauthenticated_snapshot_also_has_one_timestamp(self):
        snapshot = self.client().get_device_state()
        self.assertEqual(self.now.calls, 1)
        self.assertIs(snapshot.observed_at, OBSERVED_AT)

    def test_sanitized_observed_shapes_aggregate_without_raw_values(self):
        session = FakeSession(reconstructed_responses())
        snapshot = self.client(session).get_device_state()
        self.assert_sources(snapshot, SOURCES)
        self.assertEqual(snapshot.errors, ())
        self.assertFalse(snapshot.partial)
        self.assertEqual(snapshot.radio.bands, (1, 28))
        self.assertEqual((snapshot.radio.rsrp, snapshot.radio.secondary_rsrp), (-91, -96))
        self.assertEqual((snapshot.radio.rsrq, snapshot.radio.rssi, snapshot.radio.sinr), (-9, -82, 22))
        self.assertFalse(snapshot.radio.units_verified)
        self.assertEqual(snapshot.sim.readiness, Readiness.READY)
        self.assertIs(snapshot.sim.pin_check_enabled, False)
        self.assertEqual(snapshot.network.connection_mode, ConnectionMode.LTE)
        self.assertEqual(snapshot.network.connection, ConnectionState.CONNECTED)
        self.assertEqual(snapshot.wan.connection, ConnectionState.CONNECTED)
        self.assertIsNone(snapshot.network.registered)
        self.assertIsNone(snapshot.network.roaming)
        self.assertIsNone(snapshot.network.operator)
        self.assertFalse(snapshot.carrier_evidence.has_values)
        self.assertIsNone(snapshot.wan.apn)
        self.assertIsNone(snapshot.wan.pdp_type)
        self.assertNotIn(PRIVATE, repr(asdict(snapshot)))
        self.assert_private(snapshot)

    def test_empty_success_objects_are_complete_but_unknown(self):
        snapshot = self.client(FakeSession()).get_device_state()
        self.assertFalse(snapshot.partial)
        self.assertEqual(snapshot.radio, RadioState())
        self.assertEqual(snapshot.sim, SimState())
        self.assertEqual(snapshot.network, NetworkState())
        self.assertEqual(snapshot.wan, WanState())
        self.assertEqual(snapshot.carrier_evidence, CarrierEvidence())

    def test_one_unavailable_endpoint_preserves_other_normalized_fields(self):
        actions = reconstructed_responses()
        actions[2] = status.StatusResponse(503, {"secret": PRIVATE})
        snapshot = self.client(FakeSession(actions)).get_device_state()
        self.assert_sources(snapshot, SOURCES[:2] + SOURCES[3:])
        self.assert_issues(snapshot, ("wan",), IssueCode.UNAVAILABLE)
        self.assertEqual(snapshot.radio.bands, (1, 28))
        self.assertEqual(snapshot.sim.readiness, Readiness.READY)
        self.assertTrue(snapshot.partial)

    def test_all_non_200_http_results_are_unavailable_and_do_not_retry(self):
        session = FakeSession([status.StatusResponse(502, {"secret": PRIVATE})] * 7)
        snapshot = self.client(session).get_device_state()
        self.assertEqual(len(session.calls), 7)
        self.assert_sources(snapshot, ())
        self.assert_issues(snapshot, SOURCES, IssueCode.UNAVAILABLE)

    def test_http_auth_failures_stop_later_reads_and_preserve_earlier_success(self):
        for code in (401, 403):
            with self.subTest(code=code):
                session = FakeSession([successful_response(), successful_response(), status.StatusResponse(code, PRIVATE)])
                snapshot = self.client(session).get_device_state()
                self.assertEqual(len(session.calls), 3)
                self.assert_sources(snapshot, SOURCES[:2])
                self.assert_issues(snapshot, SOURCES[2:], IssueCode.AUTHENTICATION_REQUIRED)

    def test_body_auth_failures_stop_later_reads_and_preserve_earlier_success(self):
        for code in (401, 403):
            with self.subTest(code=code):
                session = FakeSession([successful_response(), status.StatusResponse(200, {"code": code, "msg": PRIVATE})])
                snapshot = self.client(session).get_device_state()
                self.assertEqual(len(session.calls), 2)
                self.assert_sources(snapshot, SOURCES[:1])
                self.assert_issues(snapshot, SOURCES[1:], IssueCode.AUTHENTICATION_REQUIRED)

    def test_permission_error_stops_as_authentication_required(self):
        session = FakeSession([successful_response(), PermissionError(PRIVATE)])
        snapshot = self.client(session).get_device_state()
        self.assertEqual(len(session.calls), 2)
        self.assert_sources(snapshot, SOURCES[:1])
        self.assert_issues(snapshot, SOURCES[1:], IssueCode.AUTHENTICATION_REQUIRED)

    def test_timeout_error_can_continue_within_shared_deadline(self):
        session = FakeSession([TimeoutError(PRIVATE)])
        snapshot = self.client(session).get_device_state()
        self.assertEqual(len(session.calls), 7)
        self.assert_sources(snapshot, SOURCES[1:])
        self.assert_issues(snapshot, SOURCES[:1], IssueCode.TIMEOUT)

    def test_reader_value_error_is_malformed_and_other_sources_continue(self):
        session = FakeSession([ValueError(PRIVATE)])
        snapshot = self.client(session).get_device_state()
        self.assertEqual(len(session.calls), 7)
        self.assert_sources(snapshot, SOURCES[1:])
        self.assert_issues(snapshot, SOURCES[:1], IssueCode.MALFORMED_RESPONSE)

    def test_other_reader_exception_is_unavailable_and_other_sources_continue(self):
        session = FakeSession([RuntimeError(PRIVATE)])
        snapshot = self.client(session).get_device_state()
        self.assertEqual(len(session.calls), 7)
        self.assert_sources(snapshot, SOURCES[1:])
        self.assert_issues(snapshot, SOURCES[:1], IssueCode.UNAVAILABLE)

    def test_missing_null_and_wrong_payload_types_are_malformed_not_auth(self):
        bad_payloads = (None, [], PRIVATE, {}, {"code": 200}, {"code": 200, "data": None}, {"code": 200, "data": []})
        for payload in bad_payloads:
            with self.subTest(shape=type(payload).__name__):
                session = FakeSession([status.StatusResponse(200, payload)])
                snapshot = self.client(session).get_device_state()
                self.assertEqual(len(session.calls), 7)
                self.assert_sources(snapshot, SOURCES[1:])
                self.assert_issues(snapshot, SOURCES[:1], IssueCode.MALFORMED_RESPONSE)

    def test_string_auth_code_is_malformed_and_does_not_stop_other_sources(self):
        session = FakeSession([status.StatusResponse(200, {"code": "401", "data": {}})])
        snapshot = self.client(session).get_device_state()
        self.assertEqual(len(session.calls), 7)
        self.assert_issues(snapshot, SOURCES[:1], IssueCode.MALFORMED_RESPONSE)

    def test_wrong_reader_return_types_are_malformed_and_other_sources_continue(self):
        for response in (None, PRIVATE, {"http_status": 200, "payload": {}}, object()):
            with self.subTest(response_type=type(response).__name__):
                session = FakeSession([response])
                snapshot = self.client(session).get_device_state()
                self.assertEqual(len(session.calls), 7)
                self.assert_sources(snapshot, SOURCES[1:])
                self.assert_issues(snapshot, SOURCES[:1], IssueCode.MALFORMED_RESPONSE)

    def test_wrong_http_status_types_do_not_trigger_authentication_or_success(self):
        for http_status in (True, "200", "401", 200.0, None):
            with self.subTest(status_type=type(http_status).__name__):
                session = FakeSession([status.StatusResponse(http_status, {"code": 200, "data": {}})])
                snapshot = self.client(session).get_device_state()
                self.assertEqual(len(session.calls), 7)
                self.assert_issues(snapshot, SOURCES[:1], IssueCode.MALFORMED_RESPONSE)

    def test_exception_values_are_neither_printed_logged_nor_retained(self):
        session = FakeSession([
            RuntimeError(PRIVATE), ValueError(PRIVATE), TimeoutError(PRIVATE),
            successful_response({"Authorization": PRIVATE, "SMS": PRIVATE, "OTP": PRIVATE}),
        ])
        output, logs = io.StringIO(), io.StringIO()
        handler, logger = logging.StreamHandler(logs), logging.getLogger()
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        with redirect_stdout(output), redirect_stderr(output):
            snapshot = self.client(session).get_device_state()
        self.assertNotIn(PRIVATE, output.getvalue() + logs.getvalue())
        self.assertNotIn(PRIVATE, repr(asdict(snapshot)))
        self.assert_private(snapshot)
        for issue in snapshot.errors:
            self.assertIn(issue.source, SOURCES)
            self.assertIsInstance(issue.code, IssueCode)
            self.assert_private(issue)

    def test_keyboard_interrupt_is_not_converted_into_device_unavailability(self):
        session = FakeSession([KeyboardInterrupt()])
        with self.assertRaises(KeyboardInterrupt):
            self.client(session).get_device_state()
        self.assertEqual(len(session.calls), 1)


class DeadlineAndCancellationTests(OfflineStatusCase):
    def test_invalid_timeout_values_fail_before_reader_calls(self):
        for timeout in (0, -1, float("nan"), float("inf"), -float("inf"), True, False, None, "20", 2j):
            with self.subTest(timeout_type=type(timeout).__name__):
                session = FakeSession()
                with self.assertRaises(ValueError) as caught:
                    self.client(session).get_device_state(timeout=timeout)
                self.assertEqual(session.calls, [])
                self.assertNotIn(PRIVATE, str(caught.exception))

    def test_invalid_timeout_does_not_format_arbitrary_argument(self):
        class PrivateArgument:
            def __repr__(self):
                return PRIVATE

        session = FakeSession()
        with self.assertRaises(ValueError) as caught:
            self.client(session).get_device_state(timeout=PrivateArgument())
        self.assertEqual(session.calls, [])
        self.assert_private(caught.exception)
        self.assertIsNone(caught.exception.__cause__)

    def test_set_stop_event_prevents_any_reader_call(self):
        session, stop = FakeSession(), threading.Event()
        stop.set()
        snapshot = self.client(session).get_device_state(stop_event=stop)
        self.assertEqual(session.calls, [])
        self.assert_sources(snapshot, ())
        self.assert_issues(snapshot, SOURCES, IssueCode.CANCELLED)

    def test_cancellation_during_read_discards_returned_response(self):
        stop = threading.Event()

        def cancel():
            stop.set()
            return successful_response({"Band": "1/28"})

        session = FakeSession([cancel])
        snapshot = self.client(session).get_device_state(stop_event=stop)
        self.assertEqual(len(session.calls), 1)
        self.assert_sources(snapshot, ())
        self.assert_issues(snapshot, SOURCES, IssueCode.CANCELLED)
        self.assertEqual(snapshot.radio.bands, ())

    def test_cancellation_preserves_prior_success_and_discards_current(self):
        stop = threading.Event()

        def cancel():
            stop.set()
            return successful_response({"Band": "1/28"})

        session = FakeSession([successful_response(), cancel])
        snapshot = self.client(session).get_device_state(stop_event=stop)
        self.assertEqual(len(session.calls), 2)
        self.assert_sources(snapshot, SOURCES[:1])
        self.assert_issues(snapshot, SOURCES[1:], IssueCode.CANCELLED)

    def test_cancellation_after_reader_exception_still_stops_remaining_reads(self):
        stop = threading.Event()

        def cancel_then_raise():
            stop.set()
            raise RuntimeError(PRIVATE)

        session = FakeSession([cancel_then_raise])
        snapshot = self.client(session).get_device_state(stop_event=stop)
        self.assertEqual(len(session.calls), 1)
        self.assert_issues(snapshot, SOURCES, IssueCode.CANCELLED)

    def test_deadline_expiring_before_first_read_prevents_all_requests(self):
        def expires_immediately():
            self.clock.calls += 1
            return 100.0 if self.clock.calls == 1 else 121.0

        session = FakeSession()
        client = status.D2StatusClient(session, clock=expires_immediately, now=self.now)
        snapshot = client.get_device_state(timeout=20)
        self.assertEqual(session.calls, [])
        self.assert_sources(snapshot, ())
        self.assert_issues(snapshot, SOURCES, IssueCode.TIMEOUT)

    def test_late_response_is_discarded_and_remaining_sources_time_out(self):
        def late():
            self.clock.value = 121.0
            return successful_response({"Band": "1/28"})

        session = FakeSession([successful_response(), late])
        snapshot = self.client(session).get_device_state(timeout=20)
        self.assertEqual(len(session.calls), 2)
        self.assert_sources(snapshot, SOURCES[:1])
        self.assert_issues(snapshot, SOURCES[1:], IssueCode.TIMEOUT)
        self.assertEqual(snapshot.radio.bands, ())

    def test_response_at_exact_deadline_is_discarded(self):
        def at_deadline():
            self.clock.value = 120.0
            return successful_response()

        session = FakeSession([at_deadline])
        snapshot = self.client(session).get_device_state(timeout=20)
        self.assertEqual(len(session.calls), 1)
        self.assert_sources(snapshot, ())
        self.assert_issues(snapshot, SOURCES, IssueCode.TIMEOUT)

    def test_timeout_exception_after_overall_deadline_stops_remaining_reads(self):
        def expire_and_raise():
            self.clock.value = 121.0
            raise TimeoutError(PRIVATE)

        session = FakeSession([successful_response(), expire_and_raise])
        snapshot = self.client(session).get_device_state(timeout=20)
        self.assertEqual(len(session.calls), 2)
        self.assert_sources(snapshot, SOURCES[:1])
        self.assert_issues(snapshot, SOURCES[1:], IssueCode.TIMEOUT)

    def test_late_final_read_keeps_all_six_earlier_results(self):
        def late():
            self.clock.value = 121.0
            return successful_response()

        session = FakeSession([successful_response()] * 6 + [late])
        snapshot = self.client(session).get_device_state(timeout=20)
        self.assertEqual(len(session.calls), 7)
        self.assert_sources(snapshot, SOURCES[:6])
        self.assert_issues(snapshot, SOURCES[6:], IssueCode.TIMEOUT)
        self.assertTrue(snapshot.partial)


class ModelPrivacyTests(OfflineStatusCase):
    def test_all_models_have_opaque_repr_even_with_wrong_typed_private_values(self):
        models = (
            SimState(present=PRIVATE, readiness=PRIVATE, iccid_availability=PRIVATE),
            NetworkState(operator=PRIVATE, connection=PRIVATE),
            RadioState(bands=(PRIVATE,), rsrp=PRIVATE),
            WanState(apn=PRIVATE, pdp_type=PRIVATE, ip_family=PRIVATE),
            CarrierEvidence(operator=PRIVATE, plmn=PRIVATE, mcc=PRIVATE, mnc=PRIVATE),
            DeviceIssue(source=PRIVATE, code=PRIVATE),
            DeviceState(source=PRIVATE, errors=(PRIVATE,), observed_at=PRIVATE),
            status.StatusResponse(200, {"Authorization": PRIVATE, "IP": PRIVATE, "SMS": PRIVATE}),
        )
        for model in models:
            with self.subTest(model=type(model).__name__):
                self.assert_private(model)
                self.assertIn("details omitted", repr(model))

    def test_logging_model_repr_and_str_cannot_disclose_private_values(self):
        model = DeviceState(
            network=NetworkState(operator=PRIVATE),
            wan=WanState(apn=PRIVATE),
            carrier_evidence=CarrierEvidence(operator=PRIVATE, plmn=PRIVATE),
            errors=(DeviceIssue(PRIVATE, PRIVATE),),
        )
        output = io.StringIO()
        logger = logging.Logger("d2-status-model-test")
        logger.addHandler(logging.StreamHandler(output))
        for item in (model, model.network, model.wan, model.carrier_evidence, *model.errors):
            logger.warning("state=%s repr=%r", item, item)
        self.assertNotIn(PRIVATE, output.getvalue())

    def test_status_client_repr_hides_session_and_callbacks(self):
        class PrivateCallback:
            def __repr__(self):
                return PRIVATE

            def __call__(self):
                return 100.0

        client = status.D2StatusClient(FakeSession(), clock=PrivateCallback(), now=PrivateCallback())
        self.assert_private(client)

    def test_models_and_response_reject_field_reassignment(self):
        models = (
            (SimState(), "present"), (NetworkState(), "operator"),
            (RadioState(), "bands"), (WanState(), "apn"),
            (CarrierEvidence(), "operator"), (DeviceIssue("wireless", IssueCode.TIMEOUT), "source"),
            (DeviceState(), "source"), (status.StatusResponse(200, {}), "payload"),
        )
        for model, field in models:
            with self.subTest(model=type(model).__name__):
                with self.assertRaises(FrozenInstanceError):
                    setattr(model, field, PRIVATE)

    def test_normalized_snapshot_uses_immutable_collections(self):
        snapshot = self.client(FakeSession(reconstructed_responses())).get_device_state()
        self.assertIsInstance(snapshot.radio.bands, tuple)
        self.assertIsInstance(snapshot.successful_sources, tuple)
        self.assertIsInstance(snapshot.errors, tuple)
        self.assertEqual(snapshot.sim.pin_state, PinState.UNKNOWN)
        self.assertIn(snapshot.sim.iccid_availability, tuple(Availability))

    def test_default_models_have_no_claimed_carrier_evidence(self):
        evidence = CarrierEvidence()
        self.assertFalse(evidence.has_values)
        self.assertEqual((evidence.operator, evidence.plmn, evidence.mcc, evidence.mnc), (None,) * 4)


if __name__ == "__main__":
    unittest.main()
