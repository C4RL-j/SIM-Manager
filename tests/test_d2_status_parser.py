"""Offline production parsing tests; hidden fixture contents stay unknown.

The Task 004 fixture is a filtered report, not a raw HTTP response. The helper
below reconstructs synthetic envelopes using its observed field paths/types and
retained labels. Literal masked/omitted markers are not real identifiers.
"""

from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import unittest
from unittest.mock import patch

from sim_manager.devices.d2.status_parser import SOURCE_KEYS, normalize_status
from sim_manager.models import (
    Availability, ConnectionMode, ConnectionState, DeviceIssue, IssueCode,
    PinState, Readiness,
)

OBSERVED_AT = datetime(2026, 10, 8, 1, 2, 3, tzinfo=timezone.utc)
PRIVATE = 'SYNTHETIC_PRIVATE_VALUE'
FIXTURE = Path(__file__).parent / 'fixtures' / 'd2' / 'authenticated-report.json'


def envelope(data):
    return {'code': 200, 'data': data}


def fixture_envelopes():
    """Synthetic shape reconstruction; no guess at masked/omitted values."""
    fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
    responses = {}
    for request in fixture['report']['requests']:
        data = {}
        for field_path, representation in request['summary']['fields'].items():
            parts = field_path.split('.')[1:]
            current = data
            for part in parts[:-1]:
                current = current.setdefault(part, {})
            current[parts[-1]] = representation.get('value')
        responses[request['query']] = envelope(data)
    return responses


def status_data(**fields):
    return {'wanStatus': envelope({'ConnectionStatus': fields})}


class ObservedShapeTests(unittest.TestCase):
    def test_authenticated_shape_normalizes_without_guessing_hidden_values(self):
        state = normalize_status(fixture_envelopes(), observed_at=OBSERVED_AT)
        self.assertEqual(state.successful_sources, SOURCE_KEYS)
        self.assertFalse(state.partial)
        self.assertEqual(state.errors, ())
        self.assertEqual(state.source, 'device:d2')
        self.assertEqual(state.observed_at, OBSERVED_AT)
        self.assertEqual(state.sim.readiness, Readiness.READY)
        self.assertIsNone(state.sim.present)
        self.assertEqual(state.sim.pin_state, PinState.UNKNOWN)
        self.assertIs(state.sim.pin_check_enabled, False)
        for value in (
            state.sim.iccid_availability, state.sim.imsi_availability,
            state.sim.msisdn_availability, state.wan.address_availability,
        ):
            self.assertEqual(value, Availability.UNKNOWN)
        self.assertEqual(state.network.connection_mode, ConnectionMode.LTE)
        self.assertEqual(state.network.connection, ConnectionState.CONNECTED)
        self.assertEqual(state.wan.connection, ConnectionState.CONNECTED)
        self.assertEqual(state.radio.bands, (1, 28))
        self.assertEqual(
            (state.radio.rsrp, state.radio.secondary_rsrp, state.radio.rsrq,
             state.radio.rssi, state.radio.sinr),
            (-91, -96, -9, -82, 22),
        )
        self.assertFalse(state.radio.units_verified)
        self.assertIsNone(state.radio.pci)
        self.assertIsNone(state.radio.earfcn)
        self.assertFalse(state.carrier_evidence.has_values)

    def test_empty_valid_endpoints_are_complete_retrieval_not_known_fields(self):
        state = normalize_status({key: envelope({}) for key in SOURCE_KEYS})
        self.assertFalse(state.partial)
        self.assertEqual(state.successful_sources, SOURCE_KEYS)
        self.assertEqual(state.sim.readiness, Readiness.UNKNOWN)
        self.assertEqual(state.radio.bands, ())
        self.assertEqual(state.errors, ())

    def test_unknown_fields_never_establish_carrier_or_unverified_semantics(self):
        raw = {
            'Operator': PRIVATE, 'PLMN': '51566', 'MCC': '515', 'MNC': '66',
            'Registration': True, 'Roaming': False, 'RAT': 'LTE',
            'EARFCN': 1234, 'APN': PRIVATE, 'PDPType': 'IPv4v6',
            'IPv4Address': PRIVATE, 'IPv6Address': PRIVATE, 'Present': True,
            'PINState': 'PIN_REQUIRED', 'SSID': PRIVATE,
        }
        responses = {source: envelope(deepcopy(raw)) for source in SOURCE_KEYS}
        responses['wanStatus']['data']['ConnectionStatus'] = deepcopy(raw)
        state = normalize_status(responses)
        self.assertFalse(state.partial)
        self.assertIsNone(state.network.operator)
        self.assertIsNone(state.network.registered)
        self.assertIsNone(state.network.roaming)
        self.assertEqual(state.network.connection_mode, ConnectionMode.UNKNOWN)
        self.assertFalse(state.carrier_evidence.has_values)
        self.assertIsNone(state.radio.earfcn)
        self.assertIsNone(state.wan.ip_family)
        self.assertIsNone(state.wan.apn)
        self.assertIsNone(state.wan.pdp_type)
        self.assertIsNone(state.sim.present)
        self.assertEqual(state.sim.pin_state, PinState.UNKNOWN)
        self.assertNotIn(PRIVATE, repr(asdict(state)))


class StatusPrecedenceTests(unittest.TestCase):
    def test_populated_unknown_sim_state_blocks_dashboard_ready(self):
        for value in ('ABSENT', 'SIM PIN', 'PUK', 'ready', 0, False, {}, []):
            with self.subTest(value=value):
                responses = {
                    'sim': envelope({'SIMCardState': value}),
                    'device': envelope({'USIMStatus': 'Ready'}),
                    **status_data(USIMStatus='Ready'),
                }
                state = normalize_status(responses)
                self.assertEqual(state.sim.readiness, Readiness.UNKNOWN)
                self.assertEqual(state.sim.pin_state, PinState.UNKNOWN)
                self.assertIsNone(state.sim.present)

    def test_missing_null_or_empty_sim_state_can_use_dashboard_ready(self):
        for data in ({}, {'SIMCardState': None}, {'SIMCardState': ''}, {'SIMCardState': '  '}):
            with self.subTest(data=data):
                state = normalize_status({
                    'sim': envelope(data), 'device': envelope({'USIMStatus': 'Ready'}),
                })
                self.assertEqual(state.sim.readiness, Readiness.READY)

    def test_dashboard_unknown_blocks_lower_priority_sim_ready(self):
        state = normalize_status({
            'device': envelope({'USIMStatus': 'FUTURE_STATUS'}),
            **status_data(USIMStatus='Ready'),
        })
        self.assertEqual(state.sim.readiness, Readiness.UNKNOWN)

    def test_nested_wan_can_supply_ready_when_higher_sources_missing(self):
        self.assertEqual(normalize_status(status_data(USIMStatus='Ready')).sim.readiness, Readiness.READY)

    def test_only_observed_pin_check_off_label_is_interpreted(self):
        for value in ('ON', 'off', 0, False, None, '', 'PIN', PRIVATE):
            with self.subTest(value=value):
                self.assertIsNone(normalize_status({'sim': envelope({'PINCheckEnabled': value})}).sim.pin_check_enabled)
        self.assertIs(normalize_status({'sim': envelope({'PINCheckEnabled': 'OFF'})}).sim.pin_check_enabled, False)

    def test_populated_unknown_connection_blocks_stale_internet_connected(self):
        for value in ('UNKNOWN', 'connected', True, 1, {}, []):
            with self.subTest(value=value):
                state = normalize_status({
                    **status_data(ConnectStatus=value),
                    'internet': envelope({'Status': 'Connected'}),
                })
                self.assertEqual(state.network.connection, ConnectionState.UNKNOWN)
                self.assertEqual(state.wan.connection, ConnectionState.UNKNOWN)

    def test_missing_connection_status_falls_back_but_disconnected_wins(self):
        for value in (None, '', '  '):
            with self.subTest(value=value):
                state = normalize_status({
                    **status_data(ConnectStatus=value),
                    'internet': envelope({'Status': 'Connected'}),
                })
                self.assertEqual(state.network.connection, ConnectionState.CONNECTED)
        state = normalize_status({
            **status_data(ConnectStatus='Disconnected'),
            'internet': envelope({'Status': 'Connected'}),
        })
        self.assertEqual(state.network.connection, ConnectionState.DISCONNECTED)

    def test_only_verified_nested_lte_path_establishes_mode(self):
        for value in ('GSM', 'lte', '5G', 4, None, ''):
            with self.subTest(value=value):
                state = normalize_status({
                    **status_data(ConnectMode=value),
                    'wan': envelope({'ConnectMethod': 'GSM', 'ConnectMode': 'LTE'}),
                    'internet': envelope({'ConnectMode': 'LTE'}),
                })
                self.assertEqual(state.network.connection_mode, ConnectionMode.UNKNOWN)
        self.assertEqual(normalize_status(status_data(ConnectMode='LTE')).network.connection_mode, ConnectionMode.LTE)


class RadioParsingTests(unittest.TestCase):
    def test_bands_preserve_reported_order_and_duplicates(self):
        for raw, expected in (('1/28', (1, 28)), ('28/1/28', (28, 1, 28)), (' 1 ', (1,)), ('01/028', (1, 28)), ('999', (999,))):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_status(status_data(Band=raw)).radio.bands, expected)

    def test_malformed_band_values_are_unknown(self):
        for value in (None, '', 1, True, '0', '1/0', '-1', '1//28', '1,28', '1+28', '1 /28', 'B1', '1/28/', '\uff11/\uff12\uff18', '1000', '0001', '1' * 300, '1/' * 128 + '1'):
            with self.subTest(value=value):
                self.assertEqual(normalize_status(status_data(Band=value)).radio.bands, ())

    def test_signal_numbers_and_plain_short_decimal_strings(self):
        for raw, expected in ((-91, -91.0), (-91.5, -91.5), ('-91', -91.0), (' +22.25 ', 22.25), (0, 0.0), ('0', 0.0)):
            with self.subTest(raw=raw):
                self.assertEqual(normalize_status(status_data(RSRP0=raw)).radio.rsrp, expected)

    def test_malformed_signal_values_do_not_invalidate_other_fields(self):
        invalid = (None, '', True, False, [], {}, 'NaN', 'Infinity', '1e2', '-91 dBm', '--91', '\u221291', '\uff19\uff11', float('nan'), float('inf'), -1000, 1000, 10 ** 5000)
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                state = normalize_status(status_data(RSRP0=value, RSRQ='-9', SINR='22'))
                self.assertIsNone(state.radio.rsrp)
                self.assertEqual(state.radio.rsrq, -9)
                self.assertEqual(state.radio.sinr, 22)
                self.assertEqual(state.successful_sources, ('wanStatus',))
                self.assertEqual(state.errors, ())

    def test_radio_fallback_is_independent_for_each_valid_field(self):
        state = normalize_status({
            **status_data(Band='bad', RSRP0='bad', RSRQ='-8', SINR=None, RSSI='-82', RSRP1='-96'),
            'internet': envelope({'Band': '1/28', 'RSRP': '-91', 'RSRQ': '-9', 'SINR': '22', 'RSSI': '-99'}),
        })
        self.assertEqual(state.radio.bands, (1, 28))
        self.assertEqual(state.radio.rsrp, -91)
        self.assertEqual(state.radio.rsrq, -8)
        self.assertEqual(state.radio.sinr, 22)
        self.assertEqual(state.radio.rssi, -82)
        self.assertEqual(state.radio.secondary_rsrp, -96)
        self.assertFalse(state.radio.units_verified)

    def test_pci_accepts_defensive_integer_forms_without_inventing_earfcn(self):
        for raw, expected in ((0, 0), (123, 123), (999999, 999999), ('0', 0), ('0123', 123), (' 123 ', 123), ('999999', 999999), (-1, None), (True, None), (1.0, None), ('1.0', None), ('-1', None), ('abc', None), ('', None), (None, None), (1000000, None), (10 ** 5000, None), ('1000000', None), ('0000123', None), ('\uff11\uff12\uff13', None)):
            with self.subTest(raw_type=type(raw).__name__):
                state = normalize_status(status_data(PCI=raw, EARFCN=1234))
                self.assertEqual(state.radio.pci, expected)
                self.assertIsNone(state.radio.earfcn)


class AvailabilityTests(unittest.TestCase):
    def test_presence_requires_reported_text_and_does_not_assert_validity(self):
        cases = (
            (None, Availability.UNKNOWN), (123, Availability.UNKNOWN),
            (False, Availability.UNKNOWN), ({}, Availability.UNKNOWN),
            ('', Availability.UNAVAILABLE), ('  ', Availability.UNAVAILABLE),
            ('masked', Availability.UNKNOWN), ('omitted', Availability.UNKNOWN),
            ('<masked>', Availability.UNKNOWN), ('[redacted]', Availability.UNKNOWN),
            ('********', Availability.UNKNOWN), ('xxxx', Availability.UNKNOWN),
            ('not-a-valid-identifier', Availability.AVAILABLE),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                state = normalize_status({
                    'device': envelope({'UICCID': value, 'IMSI': value}),
                    'deviceDetails': envelope({'MSISDN': value}),
                    'wan': envelope({'IpAddress': value}),
                })
                self.assertEqual(state.sim.iccid_availability, expected)
                self.assertEqual(state.sim.imsi_availability, expected)
                self.assertEqual(state.sim.msisdn_availability, expected)
                self.assertEqual(state.wan.address_availability, expected)

    def test_imsi_first_explicit_text_including_empty_or_masked_wins(self):
        for value, expected in (('', Availability.UNAVAILABLE), ('masked', Availability.UNKNOWN), (PRIVATE, Availability.AVAILABLE)):
            with self.subTest(value=value):
                state = normalize_status({
                    'device': envelope({'IMSI': value}),
                    **status_data(IMSI=PRIVATE),
                    'deviceDetails': envelope({'IMSI': PRIVATE}),
                })
                self.assertEqual(state.sim.imsi_availability, expected)

    def test_imsi_missing_or_nonstrings_can_fall_back(self):
        for value in (None, 123, False, []):
            with self.subTest(value=value):
                state = normalize_status({
                    'device': envelope({'IMSI': value}),
                    **status_data(IMSI=PRIVATE),
                })
                self.assertEqual(state.sim.imsi_availability, Availability.AVAILABLE)
        state = normalize_status({'deviceDetails': envelope({'IMSI': PRIVATE})})
        self.assertEqual(state.sim.imsi_availability, Availability.AVAILABLE)

    def test_only_verified_identity_and_wan_address_paths_are_read(self):
        state = normalize_status({
            'device': envelope({'ICCID': PRIVATE, 'MSISDN': PRIVATE, 'IpAddress': PRIVATE}),
            'sim': envelope({'UICCID': PRIVATE, 'IMSI': PRIVATE, 'MSISDN': PRIVATE}),
            'deviceDetails': envelope({'UICCID': PRIVATE, 'IpAddress': PRIVATE}),
        })
        self.assertEqual(state.sim.iccid_availability, Availability.UNKNOWN)
        self.assertEqual(state.sim.imsi_availability, Availability.UNKNOWN)
        self.assertEqual(state.sim.msisdn_availability, Availability.UNKNOWN)
        self.assertEqual(state.wan.address_availability, Availability.UNKNOWN)


class EnvelopeAndPrivacyTests(unittest.TestCase):
    def test_missing_endpoints_are_partial_without_fabricated_errors(self):
        state = normalize_status({'internet': envelope({'RSRP': '-91'})})
        self.assertTrue(state.partial)
        self.assertEqual(state.successful_sources, ('internet',))
        self.assertEqual(state.errors, ())
        self.assertEqual(state.radio.rsrp, -91)

    def test_provided_bad_envelopes_add_only_sanitized_fixed_source_issues(self):
        invalid = (None, [], PRIVATE, {}, {'code': True, 'data': {}},
                   {'code': 200.0, 'data': {}}, {'code': '200', 'data': {}},
                   {'code': 401, 'msg': PRIVATE, 'data': {}},
                   {'code': 200, 'data': None}, {'code': 200, 'data': []},
                   {'code': 200, 'data': PRIVATE})
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                state = normalize_status({'sim': value, 'internet': envelope({'RSRP': '-91'})})
                self.assertTrue(state.partial)
                self.assertEqual(state.successful_sources, ('internet',))
                self.assertEqual(state.errors, (DeviceIssue('sim', IssueCode.MALFORMED_RESPONSE),))
                self.assertEqual(state.radio.rsrp, -91)
                self.assertNotIn(PRIVATE, repr(asdict(state)))

    def test_unexpected_nested_connection_shape_does_not_crash(self):
        for value in (None, [], '', PRIVATE, True, 123):
            with self.subTest(value_type=type(value).__name__):
                state = normalize_status({'wanStatus': envelope({'ConnectionStatus': value})})
                self.assertEqual(state.successful_sources, ('wanStatus',))
                self.assertEqual(state.errors, ())
                self.assertEqual(state.network.connection, ConnectionState.UNKNOWN)

    def test_unknown_endpoint_keys_and_response_messages_are_not_retained(self):
        state = normalize_status({
            PRIVATE: envelope({'IMSI': PRIVATE}),
            'wireless': {'code': 200, 'data': {}, 'msg': PRIVATE, 'Authorization': PRIVATE},
        })
        self.assertEqual(state.successful_sources, ('wireless',))
        self.assertEqual(state.errors, ())
        self.assertNotIn(PRIVATE, repr(asdict(state)))

    def test_safe_external_issues_are_preserved_and_invalid_values_discarded(self):
        issue = DeviceIssue('sim', IssueCode.TIMEOUT)
        state = normalize_status({}, errors=(
            issue, issue, DeviceIssue(PRIVATE, IssueCode.UNAVAILABLE),
            DeviceIssue('device', PRIVATE), PRIVATE,
        ))
        self.assertEqual(state.errors, (issue,))
        self.assertTrue(state.partial)
        self.assertNotIn(PRIVATE, repr(asdict(state)))

    def test_error_prevents_complete_flag_even_if_responses_are_all_valid(self):
        state = normalize_status(
            {key: envelope({}) for key in SOURCE_KEYS},
            errors=(DeviceIssue('sim', IssueCode.UNAVAILABLE),),
        )
        self.assertTrue(state.partial)
        self.assertEqual(state.successful_sources, SOURCE_KEYS)

    def test_discarded_unsafe_issues_do_not_change_retrieval_completeness(self):
        state = normalize_status(
            {key: envelope({}) for key in SOURCE_KEYS},
            errors=(DeviceIssue(PRIVATE, IssueCode.UNAVAILABLE), DeviceIssue('sim', PRIVATE), PRIVATE),
        )
        self.assertFalse(state.partial)
        self.assertEqual(state.errors, ())
        self.assertNotIn(PRIVATE, repr(asdict(state)))

    def test_filtered_report_is_not_mistaken_for_raw_json_envelopes(self):
        report = json.loads(FIXTURE.read_text(encoding='utf-8'))['report']
        state = normalize_status(report)
        self.assertEqual(state.successful_sources, ())
        self.assertEqual(state.errors, ())
        summary = report['requests'][1]['summary']
        state = normalize_status({'internet': summary})
        self.assertEqual(state.errors, (DeviceIssue('internet', IssueCode.MALFORMED_RESPONSE),))

    def test_normalization_is_immutable_independent_and_private_in_logs(self):
        responses = fixture_envelopes()
        responses['device']['data'].update({'UICCID': PRIVATE, 'IMSI': PRIVATE, 'Authorization': PRIVATE})
        responses['wan']['data'].update({'IpAddress': PRIVATE, 'DnsServer': PRIVATE, 'APN': PRIVATE})
        before = deepcopy(responses)
        with patch('socket.create_connection', side_effect=AssertionError('No hardware')), patch('socket.socket', side_effect=AssertionError('No hardware')):
            state = normalize_status(responses, observed_at=OBSERVED_AT)
        self.assertEqual(responses, before)
        responses['internet']['data']['RSRP'] = '-20'
        responses['wanStatus']['data']['ConnectionStatus']['RSRP0'] = '-20'
        self.assertEqual(state.radio.rsrp, -91)
        self.assertNotIn(PRIVATE, repr(asdict(state)))
        for model in (state, state.sim, state.network, state.radio, state.wan, state.carrier_evidence):
            self.assertIn('<details omitted>', repr(model))
            self.assertNotIn(PRIVATE, str(model))
        for model, attribute, value in ((state, 'partial', False), (state.sim, 'present', True), (state.radio, 'rsrp', 0)):
            with self.subTest(attribute=attribute), self.assertRaises(FrozenInstanceError):
                setattr(model, attribute, value)
        with self.assertLogs('parser-privacy', level='INFO') as captured:
            logging.getLogger('parser-privacy').info('state=%s sim=%r', state, state.sim)
        self.assertNotIn(PRIVATE, '\n'.join(captured.output))

    def test_default_observation_time_is_aware_utc(self):
        self.assertEqual(normalize_status({}).observed_at.tzinfo, timezone.utc)


if __name__ == '__main__':
    unittest.main()
