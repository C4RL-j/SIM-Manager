"""Offline service/demo and privacy-safe presentation behavior."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError, asdict, replace
from datetime import datetime, timezone
from importlib.resources import files
from io import StringIO
from pathlib import Path
from threading import Event
import unittest
from unittest.mock import patch

from sim_manager.account_models import AccountBucket, AccountData, AccountPromo
from sim_manager.devices.d2.demo import load_demo_state
from sim_manager.devices.d2.status_parser import SOURCE_KEYS
from sim_manager.models import (
    Availability, CarrierEvidence, ConnectionMode, ConnectionState, DeviceIssue,
    DeviceState, IssueCode, NetworkState, PinState, RadioState, Readiness,
    SimState, WanState,
)
from sim_manager.services.device import (
    DemoDeviceService, LiveDeviceService, RefreshCancelled,
)
from sim_manager.services.presentation import present_device, present_promo_expiry


PRIVATE = "SYNTHETIC_PRIVATE_VALUE"
FIRST = datetime(2026, 10, 8, 1, 2, 3, tzinfo=timezone.utc)
SECOND = datetime(2026, 10, 8, 1, 2, 4, tzinfo=timezone.utc)


class FakeClient:
    def __init__(self, state=None, stop=None):
        self.state = state if state is not None else DeviceState()
        self.stop = stop
        self.calls = []

    def get_device_state(self, **kwargs):
        self.calls.append(kwargs)
        if self.stop is not None:
            self.stop.set()
        return self.state


def known_state(**changes):
    state = DeviceState(
        sim=SimState(readiness=Readiness.READY, pin_check_enabled=False),
        network=NetworkState(connection_mode=ConnectionMode.LTE, connection=ConnectionState.CONNECTED),
        radio=RadioState(bands=(1, 28), rsrp=-91, secondary_rsrp=-96, rsrq=-9, rssi=-82, sinr=22),
        wan=WanState(connection=ConnectionState.CONNECTED, address_availability=Availability.AVAILABLE),
        successful_sources=SOURCE_KEYS, partial=False,
    )
    return replace(state, **changes)


class ProviderTests(unittest.TestCase):
    def test_default_live_service_requires_authentication_without_io_or_demo(self):
        with patch("socket.socket", side_effect=AssertionError("No hardware")), patch("socket.create_connection", side_effect=AssertionError("No hardware")), patch("sim_manager.services.device.load_demo_state", side_effect=AssertionError("No implicit demo")):
            service = LiveDeviceService()
            state = service.get_device_state()
        self.assertIs(service.is_demo, False)
        self.assertEqual(state.source, "device:d2")
        self.assertEqual(state.successful_sources, ())
        self.assertTrue(state.partial)
        self.assertEqual({issue.code for issue in state.errors}, {IssueCode.AUTHENTICATION_REQUIRED})
        self.assertEqual(present_device(state).notice, "Authentication required")

    def test_live_service_forwards_existing_client_deadline_and_cancellation(self):
        expected = known_state()
        client = FakeClient(expected)
        stop = Event()
        actual = LiveDeviceService(client).get_device_state(stop_event=stop)
        self.assertIs(actual, expected)
        self.assertEqual(client.calls, [{"timeout": 20.0, "stop_event": stop}])

    def test_live_cancelled_before_read_does_not_call_client(self):
        stop = Event()
        stop.set()
        client = FakeClient()
        with self.assertRaisesRegex(RefreshCancelled, r"^Refresh cancelled\.$"):
            LiveDeviceService(client).get_device_state(stop_event=stop)
        self.assertEqual(client.calls, [])

    def test_live_cancelled_during_read_discards_late_snapshot(self):
        stop = Event()
        client = FakeClient(known_state(), stop=stop)
        with self.assertRaisesRegex(RefreshCancelled, r"^Refresh cancelled\.$"):
            LiveDeviceService(client).get_device_state(stop_event=stop)
        self.assertEqual(len(client.calls), 1)

    def test_demo_cancelled_before_read_does_not_load_resource(self):
        stop = Event()
        stop.set()
        with patch("sim_manager.services.device.load_demo_state", side_effect=AssertionError("No resource read")):
            with self.assertRaises(RefreshCancelled):
                DemoDeviceService().get_device_state(stop_event=stop)

    def test_demo_cancelled_during_load_discards_snapshot(self):
        stop = Event()

        def load():
            stop.set()
            return known_state(source="demo:d2")

        with patch("sim_manager.services.device.load_demo_state", side_effect=load):
            with self.assertRaisesRegex(RefreshCancelled, r"^Refresh cancelled\.$"):
                DemoDeviceService().get_device_state(stop_event=stop)


class DemoTests(unittest.TestCase):
    def test_packaged_report_is_exact_copy_of_sanitized_task004_fixture(self):
        packaged = files("sim_manager.resources").joinpath("d2-demo-report.json").read_bytes()
        original = (Path(__file__).parent / "fixtures" / "d2" / "authenticated-report.json").read_bytes()
        self.assertEqual(packaged, original)

    def test_demo_is_explicit_offline_and_preserves_unknown_hidden_values(self):
        with patch("socket.socket", side_effect=AssertionError("No hardware")), patch("socket.create_connection", side_effect=AssertionError("No hardware")), patch("sim_manager.devices.d2.status.D2StatusClient.get_device_state", side_effect=AssertionError("No live client")):
            service = DemoDeviceService()
            state = service.get_device_state()
        self.assertIs(service.is_demo, True)
        self.assertEqual(state.source, "demo:d2")
        self.assertEqual(state.successful_sources, SOURCE_KEYS)
        self.assertFalse(state.partial)
        self.assertEqual(state.errors, ())
        self.assertEqual(state.sim.readiness, Readiness.READY)
        self.assertIs(state.sim.pin_check_enabled, False)
        self.assertEqual(state.radio.bands, (1, 28))
        self.assertEqual((state.radio.rsrp, state.radio.secondary_rsrp, state.radio.rsrq, state.radio.rssi, state.radio.sinr), (-91, -96, -9, -82, 22))
        self.assertIsNone(state.sim.present)
        self.assertEqual(state.sim.imsi_availability, Availability.UNKNOWN)
        self.assertEqual(state.sim.iccid_availability, Availability.UNKNOWN)
        self.assertEqual(state.sim.msisdn_availability, Availability.UNKNOWN)
        self.assertEqual(state.wan.address_availability, Availability.UNKNOWN)
        self.assertIsNone(state.radio.pci)
        self.assertIsNone(state.radio.earfcn)
        self.assertFalse(state.radio.units_verified)
        self.assertIsNone(state.network.registered)
        self.assertIsNone(state.network.roaming)
        self.assertIsNone(state.wan.ip_family)
        self.assertIsNone(state.wan.apn)
        self.assertFalse(state.carrier_evidence.has_values)

    def test_demo_refresh_gets_new_utc_observation_time(self):
        with patch("sim_manager.devices.d2.status_parser.datetime") as clock:
            clock.now.side_effect = [FIRST, SECOND]
            service = DemoDeviceService()
            first = service.get_device_state()
            second = service.get_device_state()
        self.assertEqual(first.observed_at, FIRST)
        self.assertEqual(second.observed_at, SECOND)
        self.assertIsNot(first, second)

    def test_demo_loader_accepts_deterministic_timestamp_without_relabeling_live_state(self):
        self.assertEqual(load_demo_state(observed_at=FIRST).observed_at, FIRST)
        live = LiveDeviceService().get_device_state()
        self.assertEqual(live.source, "device:d2")
        self.assertEqual(live.radio.bands, ())


class PresentationTests(unittest.TestCase):
    def test_known_snapshot_uses_only_expected_literals_and_numeric_values(self):
        view = present_device(known_state())
        self.assertEqual((view.sim_state, view.pin, view.network_mode, view.network_status, view.carrier), ("Ready", "Off", "LTE", "Connected", "Unknown"))
        self.assertEqual((view.rsrp, view.secondary_rsrp, view.rsrq, view.rssi, view.sinr, view.bands), ("-91", "-96", "-9", "-82", "22", "1 / 28"))
        self.assertEqual((view.wan_state, view.address, view.router_status, view.notice, view.level), ("Connected", "Reported", "Status available", "", "ok"))

    def test_unknown_snapshot_has_clear_missing_values(self):
        view = present_device(DeviceState())
        self.assertEqual((view.sim_state, view.pin, view.network_mode, view.network_status, view.carrier, view.wan_state, view.address), ("Unknown",) * 7)
        self.assertEqual((view.rsrp, view.secondary_rsrp, view.rsrq, view.rssi, view.sinr, view.bands), ("—",) * 6)
        self.assertEqual(view.router_status, "Router status unavailable")

    def test_only_explicit_absence_or_required_pin_can_report_sim_not_ready(self):
        cases = (
            (SimState(present=False), "Not Ready"),
            (SimState(present=False, readiness=Readiness.READY), "Not Ready"),
            (SimState(pin_state=PinState.PIN_REQUIRED), "Not Ready"),
            (SimState(pin_state=PinState.PUK_REQUIRED, readiness=Readiness.READY), "Not Ready"),
            (SimState(present=True), "Unknown"),
            (SimState(pin_check_enabled=True), "Unknown"),
            (SimState(present=0), "Unknown"),
            (SimState(pin_state="pin_required"), "Unknown"),
            (SimState(readiness=Readiness.READY), "Ready"),
            (SimState(present=True, readiness=Readiness.READY), "Ready"),
        )
        for sim, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(present_device(known_state(sim=sim)).sim_state, expected)

    def test_successful_router_or_connected_wan_does_not_establish_mobile_network(self):
        view = present_device(known_state(network=NetworkState()))
        self.assertEqual(view.router_status, "Status available")
        self.assertEqual(view.wan_state, "Connected")
        self.assertEqual(view.network_mode, "Unknown")
        self.assertEqual(view.network_status, "Unknown")

    def test_partial_retrieval_preserves_successful_fields(self):
        view = present_device(known_state(successful_sources=("wanStatus",), partial=True))
        self.assertEqual(view.rsrp, "-91")
        self.assertEqual(view.network_status, "Connected")
        self.assertEqual((view.router_status, view.notice, view.level), ("Partial data", "Partial device data", "warning"))

    def test_network_connected_does_not_claim_router_retrieval(self):
        view = present_device(known_state(successful_sources=(), partial=True))
        self.assertEqual(view.network_status, "Connected")
        self.assertEqual(view.router_status, "Router status unavailable")

    def test_friendly_error_notices_never_display_source_or_raw_error(self):
        cases = (
            (IssueCode.AUTHENTICATION_REQUIRED, "Authentication required"),
            (IssueCode.UNAVAILABLE, "Router status unavailable"),
            (IssueCode.TIMEOUT, "Router status unavailable"),
            (IssueCode.MALFORMED_RESPONSE, "Malformed response"),
            (IssueCode.CANCELLED, "Refresh cancelled"),
        )
        for code, message in cases:
            with self.subTest(code=code):
                state = known_state(errors=(DeviceIssue(PRIVATE, code),), partial=True)
                view = present_device(state)
                self.assertEqual(view.notice, message)
                self.assertEqual(view.router_status, "Partial data")
                self.assertEqual(view.rsrp, "-91")
                self.assertNotIn(PRIVATE, repr(asdict(view)))

    def test_cancellation_then_authentication_have_error_precedence(self):
        errors = tuple(DeviceIssue("sim", code) for code in (IssueCode.UNAVAILABLE, IssueCode.MALFORMED_RESPONSE, IssueCode.AUTHENTICATION_REQUIRED, IssueCode.CANCELLED))
        view = present_device(known_state(errors=errors, partial=True))
        self.assertEqual(view.notice, "Refresh cancelled")
        self.assertEqual(present_device(known_state(errors=errors[:-1], partial=True)).notice, "Authentication required")

    def test_wrong_typed_enum_strings_and_pin_flags_are_not_interpreted(self):
        view = present_device(known_state(
            sim=SimState(readiness="ready", pin_state=PRIVATE, pin_check_enabled=0),
            network=NetworkState(connection_mode="lte", connection="connected"),
            wan=WanState(connection="disconnected", address_availability="available"),
        ))
        self.assertEqual((view.sim_state, view.pin, view.network_mode, view.network_status, view.wan_state, view.address), ("Unknown",) * 6)

    def test_pin_and_address_state_use_closed_labels(self):
        for pin_state, enabled, expected in ((PinState.PIN_REQUIRED, False, "PIN required"), (PinState.PUK_REQUIRED, False, "PUK required"), (PinState.UNKNOWN, True, "On"), (PinState.UNKNOWN, False, "Off")):
            with self.subTest(expected=expected):
                self.assertEqual(present_device(known_state(sim=SimState(pin_state=pin_state, pin_check_enabled=enabled))).pin, expected)
        self.assertEqual(present_device(known_state(wan=WanState(address_availability=Availability.UNAVAILABLE))).address, "Not reported")

    def test_invalid_nested_models_and_private_optional_text_never_reach_display(self):
        states = (
            known_state(sim=PRIVATE, network=PRIVATE, radio=PRIVATE, wan=PRIVATE),
            known_state(network=NetworkState(operator=PRIVATE), wan=WanState(apn=PRIVATE, ip_family=PRIVATE, pdp_type=PRIVATE), carrier_evidence=CarrierEvidence(operator=PRIVATE, plmn=PRIVATE, mcc=PRIVATE, mnc=PRIVATE), observed_at=PRIVATE, source=PRIVATE),
        )
        for state in states:
            with self.subTest(state_type=type(state).__name__):
                view = present_device(state)
                self.assertNotIn(PRIVATE, repr(asdict(view)))
                self.assertEqual(view.carrier, "Unknown")
                self.assertTrue(all(type(value) is str for value in asdict(view).values()))

    def test_numeric_display_rejects_private_strings_booleans_and_unbounded_values(self):
        invalid = (PRIVATE, "-91", True, None, {}, [], float("nan"), float("inf"), -1000, 1000, 10 ** 5000)
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                view = present_device(known_state(radio=RadioState(rsrp=value, secondary_rsrp=value, rsrq=value, rssi=value, sinr=value)))
                self.assertEqual((view.rsrp, view.secondary_rsrp, view.rsrq, view.rssi, view.sinr), ("—",) * 5)
                self.assertNotIn(PRIVATE, repr(asdict(view)))
        self.assertEqual(present_device(known_state(radio=RadioState(rsrp=-91.5))).rsrp, "-91.5")

    def test_bands_are_validated_before_formatting(self):
        for bands in (PRIVATE, [1, 28], (True,), (0,), (1000,), (PRIVATE,), (10 ** 5000,), (999,) * 100):
            with self.subTest(value_type=type(bands).__name__):
                self.assertEqual(present_device(known_state(radio=RadioState(bands=bands))).bands, "—")
        self.assertEqual(present_device(known_state(radio=RadioState(bands=(28, 1, 28)))).bands, "28 / 1 / 28")

    def test_malformed_error_metadata_is_friendly_and_private(self):
        for errors in ((PRIVATE,), (DeviceIssue("sim", PRIVATE),), PRIVATE, None):
            with self.subTest(value_type=type(errors).__name__):
                view = present_device(known_state(errors=errors))
                self.assertEqual(view.notice, "Unknown error")
                self.assertEqual(view.router_status, "Partial data")
                self.assertNotIn(PRIVATE, repr(asdict(view)))

    def test_malformed_sources_do_not_claim_success_or_display_their_contents(self):
        for sources in ((PRIVATE,), ["sim"], ("sim", "sim"), PRIVATE, None):
            with self.subTest(value_type=type(sources).__name__):
                view = present_device(known_state(successful_sources=sources))
                self.assertEqual(view.notice, "Unknown error")
                self.assertEqual(view.router_status, "Router status unavailable")
                self.assertNotIn(PRIVATE, repr(asdict(view)))

    def test_view_is_immutable_and_diagnostics_are_opaque(self):
        view = present_device(known_state())
        self.assertEqual(repr(view), "DeviceView(<details omitted>)")
        with self.assertRaises(FrozenInstanceError):
            view.carrier = PRIVATE

    def test_invalid_top_level_snapshot_is_friendly_and_private(self):
        view = present_device(PRIVATE)
        self.assertEqual(view.notice, "Unknown error")
        self.assertNotIn(PRIVATE, repr(asdict(view)))


class PromoExpiryPresentationTests(unittest.TestCase):
    def test_load_expiry_never_becomes_promo_expiry_and_one_reported_promo_keeps_its_date(self):
        load = AccountData(updated_at=FIRST, expiry="2029-12-31")
        self.assertEqual(present_promo_expiry(None), "Not available")
        self.assertEqual(present_promo_expiry(PRIVATE), "Not available")
        self.assertEqual(present_promo_expiry(load), "Not available")
        promo = replace(load, active_promos=(AccountPromo("Synthetic plan", "2026-11-01"),))
        self.assertEqual(present_promo_expiry(promo), "2026-11-01")
        self.assertEqual(promo.expiry, "2029-12-31")

    def test_multiple_and_partial_promo_dates_keep_each_label_without_choosing_one_date(self):
        data = AccountData(updated_at=FIRST, active_promos=(
            AccountPromo("Synthetic later plan", "2026-12-01"),
            AccountPromo("Synthetic unknown plan"),
            AccountPromo("Synthetic earlier plan", "2026-10-30"),
        ), data_buckets=(AccountBucket("Synthetic bucket", "2 GB", "2026-10-20"),))
        self.assertEqual(present_promo_expiry(data),
                         "Synthetic later plan: 2026-12-01\n"
                         "Synthetic unknown plan: Not available\n"
                         "Synthetic earlier plan: 2026-10-30")

    def test_data_bucket_fallback_uses_reported_units_not_names_or_sms_call_expiries(self):
        data = AccountData(updated_at=FIRST, expiry="2029-12-31", data_buckets=(
            AccountBucket("Synthetic 5G data name", "10 SMS", "2026-10-01"),
            AccountBucket("Synthetic data name", "5 mins", "2026-10-02"),
            AccountBucket("Synthetic GB name", "Unlimited", "2026-10-03"),
            AccountBucket("Synthetic unknown unit", "10", "2026-10-04"),
            AccountBucket("Synthetic later allowance", "1,024.00 MiB", "2026-12-01"),
            AccountBucket("Synthetic undated allowance", "0.00 GB"),
            AccountBucket("Synthetic earlier allowance", "2 GB", "2026-11-01"),
        ))
        self.assertEqual(present_promo_expiry(data),
                         "Synthetic later allowance: 2026-12-01\n"
                         "Synthetic undated allowance: Not available\n"
                         "Synthetic earlier allowance: 2026-11-01")
        for quantity in ("1 B", "2 kB", "3 KB", "4 MB", "5 TB", "6 KiB", "7 GiB"):
            single = replace(data, data_buckets=(AccountBucket("Synthetic bucket", quantity, "2026-11-02"),))
            self.assertEqual(present_promo_expiry(single), "Synthetic bucket: 2026-11-02")

    def test_missing_ambiguous_dates_are_unavailable_and_display_text_is_never_logged(self):
        for quantity in (None, "Unlimited", "1 GB per day", "GB", "10 calls"):
            data = AccountData(updated_at=FIRST, active_promos=(AccountPromo("Synthetic plan"),),
                               data_buckets=(AccountBucket("Synthetic data", quantity, "2026-11-01"),))
            self.assertEqual(present_promo_expiry(data), "Not available")
        undated = AccountData(updated_at=FIRST, data_buckets=(AccountBucket("Synthetic", "1 GB"),))
        self.assertEqual(present_promo_expiry(undated), "Not available")
        literal = AccountData(updated_at=FIRST, data_buckets=(
            AccountBucket("<b>Synthetic reported label</b>", "1 GB", "2026-11-01"),
        ))
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output), self.assertNoLogs(level="DEBUG"):
            label = present_promo_expiry(literal)
        self.assertEqual(label, "<b>Synthetic reported label</b>: 2026-11-01")
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("Synthetic reported label", repr(literal))


if __name__ == "__main__":
    unittest.main()
