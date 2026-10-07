"""Offline characterization of the unchanged D2 Telnet/UBus transport.

Every fixture is synthetic. Real socket creation is blocked, and all deadlines
use a deterministic fake clock. Tests named ``legacy_quirk`` record limitations
of the copied baseline, not the intended contract after future hardening.
"""

from collections import deque
from contextlib import ExitStack
import json
import socket
import unittest
from unittest.mock import call, patch


# Importing the package must also be inert, with no device/browser startup.
with patch("socket.socket", side_effect=AssertionError("Real sockets forbidden")):
    with patch(
        "socket.create_connection",
        side_effect=AssertionError("Real connections forbidden"),
    ):
        from sim_manager.devices.d2 import router


MARKER = "__DITO_HELPER_END_91F7__"
COMMAND = (
    'ubus -t 10 call cped cmd \'{"cmd":"sms.get.inboxdata",'
    '"arg":"{\\"StartPos\\":0,\\"ReadNum\\":3}"}\''
    f"; echo {MARKER}\r\n"
)
PAYLOAD = {"code": 200, "msg": "ok", "data": []}


class FakeClock:
    """Advance on clock reads and simulated I/O, never on wall-clock time."""

    def __init__(self):
        self.now = 100.0

    def time(self):
        value = self.now
        self.now += 0.01
        return value

    def advance(self, seconds):
        self.now += seconds


class FakeSocket:
    """Script receives as bytes or exceptions and record all socket activity."""

    def __init__(self, clock, receives=(), send_error=None):
        self.clock = clock
        self.receives = deque(receives)
        self.send_error = send_error
        self.events = []
        self.sent = []
        self.timeout = 0.5
        self.closed = False

    def __enter__(self):
        self.events.append(("enter",))
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def close(self):
        self.closed = True
        self.events.append(("close",))

    def settimeout(self, timeout):
        self.timeout = timeout
        self.events.append(("settimeout", timeout))

    def sendall(self, data):
        self.events.append(("send", data))
        self.sent.append(data)
        if self.send_error is not None:
            raise self.send_error

    def recv(self, size):
        event = self.receives.popleft() if self.receives else socket.timeout()
        self.events.append(("recv", size, event))
        self.clock.advance(self.timeout if isinstance(event, socket.timeout) else 0.01)
        if isinstance(event, BaseException):
            raise event
        return event


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self.stack = self.enterContext(ExitStack())
        self.clock = FakeClock()
        self.stack.enter_context(patch.object(router.time, "time", self.clock.time))
        self.stack.enter_context(
            patch("socket.socket", side_effect=AssertionError("Real sockets forbidden"))
        )
        self.connection = self.stack.enter_context(
            patch(
                "socket.create_connection",
                side_effect=AssertionError("An explicit fake connection is required"),
            )
        )

    def fake_connection(self, receives):
        sock = FakeSocket(self.clock, receives)
        self.connection.side_effect = None
        self.connection.return_value = sock
        return sock

    def transcript(self, command_output):
        """Banner and wake-up reads end on their respective socket timeouts."""
        return [
            b"synthetic shell\r\n# ", socket.timeout(),
            b"# ", socket.timeout(), *command_output,
        ]

    def completed_output(self, payload=PAYLOAD):
        return [
            COMMAND.encode(),
            b"shell notice\r\n" + json.dumps(payload).encode() + b"\r\n",
            MARKER.encode() + b"\r\n# ",
        ]


class FetchCharacterizationTests(OfflineCase):
    def test_success_preserves_endpoint_command_pacing_and_socket_close(self):
        sock = self.fake_connection(self.transcript(self.completed_output()))
        with patch.object(router, "receive_some", wraps=router.receive_some) as reads:
            result = router.fetch_sms_response()

        self.assertEqual(result, PAYLOAD)
        self.connection.assert_called_once_with(("192.168.1.1", 2323), timeout=3.0)
        self.assertEqual(reads.call_args_list, [call(sock, 0.7), call(sock, 0.25)])
        self.assertEqual(sock.sent, [b"\r\n", COMMAND.encode()])
        self.assertEqual(sock.events[0:2], [("enter",), ("settimeout", 0.5)])
        self.assertEqual(
            [event[0] for event in sock.events],
            [
                "enter", "settimeout", "recv", "recv", "send", "recv", "recv",
                "send", "recv", "recv", "recv", "close",
            ],
        )
        self.assertTrue(sock.closed)

    def test_configured_endpoint_read_count_and_timeout_are_forwarded(self):
        command = COMMAND.replace('ReadNum\\":3', 'ReadNum\\":7')
        sock = self.fake_connection(
            self.transcript([command.encode(), json.dumps(PAYLOAD).encode(), MARKER.encode()])
        )
        with patch.object(
            router, "receive_until_marker_printed", wraps=router.receive_until_marker_printed
        ) as reads:
            self.assertEqual(
                router.fetch_sms_response("router.invalid", 1234, 7, 1.25, 4.0), PAYLOAD
            )
        self.connection.assert_called_once_with(("router.invalid", 1234), timeout=1.25)
        reads.assert_called_once_with(sock, MARKER, timeout=4.0)
        self.assertEqual(sock.sent, [b"\r\n", command.encode()])

    def test_negotiation_in_banner_and_response_is_refused_without_payload_loss(self):
        response = self.completed_output()
        response[1] = bytes([255, 253, 3]) + response[1]
        sock = self.fake_connection(
            [bytes([255, 251, 1]) + b"# ", socket.timeout(), b"# ", socket.timeout(), *response]
        )
        self.assertEqual(router.fetch_sms_response(), PAYLOAD)
        self.assertEqual(
            sock.sent,
            [bytes([255, 254, 1]), b"\r\n", COMMAND.encode(), bytes([255, 252, 3])],
        )
        self.assertTrue(sock.closed)

    def test_echo_does_not_complete_read_before_fragmented_final_marker(self):
        payload = json.dumps(PAYLOAD).encode()
        sock = self.fake_connection(
            self.transcript(
                [
                    COMMAND.encode(), payload[:12], payload[12:],
                    MARKER[:9].encode(), MARKER[9:].encode(), b"unread trailing prompt",
                ]
            )
        )
        self.assertEqual(router.fetch_sms_response(), PAYLOAD)
        self.assertEqual(list(sock.receives), [b"unread trailing prompt"])

    def test_response_receive_timeouts_are_retried_until_completion(self):
        output = self.completed_output()
        sock = self.fake_connection(
            self.transcript([socket.timeout(), output[0], socket.timeout(), *output[1:]])
        )
        self.assertEqual(router.fetch_sms_response(response_timeout=3.0), PAYLOAD)
        self.assertTrue(sock.closed)

    def test_legacy_quirk_echo_disabled_shell_times_out_after_valid_response(self):
        sock = self.fake_connection(
            self.transcript([json.dumps(PAYLOAD).encode(), MARKER.encode()])
        )
        with self.assertRaisesRegex(router.RouterTimeoutError, "SMS command to finish"):
            router.fetch_sms_response(response_timeout=1.0)
        self.assertTrue(sock.closed)

    def test_missing_final_marker_times_out_even_with_echo_and_valid_json(self):
        sock = self.fake_connection(self.transcript(self.completed_output()[:2]))
        with self.assertRaisesRegex(router.RouterTimeoutError, "SMS command to finish"):
            router.fetch_sms_response(response_timeout=1.0)
        self.assertTrue(sock.closed)

    def test_no_command_response_expires_on_fake_deadline(self):
        sock = self.fake_connection(self.transcript([]))
        started = self.clock.now
        with self.assertRaisesRegex(router.RouterTimeoutError, "SMS command to finish"):
            router.fetch_sms_response(response_timeout=1.0)
        self.assertGreaterEqual(self.clock.now - started, 1.0)
        self.assertLess(self.clock.now - started, 3.0)
        self.assertTrue(sock.closed)

    def test_connect_timeout_maps_to_router_timeout_with_original_cause(self):
        error = socket.timeout("synthetic timeout")
        self.connection.side_effect = error
        with self.assertRaisesRegex(router.RouterTimeoutError, "connecting to the router") as raised:
            router.fetch_sms_response()
        self.assertIs(raised.exception.__cause__, error)

    def test_connection_refusal_maps_to_connection_error(self):
        error = ConnectionRefusedError("synthetic refusal")
        self.connection.side_effect = error
        with self.assertRaisesRegex(router.RouterConnectionError, "Connection refused") as raised:
            router.fetch_sms_response()
        self.assertIs(raised.exception.__cause__, error)

    def test_connect_oserror_maps_to_connection_error(self):
        error = OSError("synthetic unavailable endpoint")
        self.connection.side_effect = error
        with self.assertRaisesRegex(router.RouterConnectionError, "Could not connect") as raised:
            router.fetch_sms_response()
        self.assertIs(raised.exception.__cause__, error)

    def test_login_or_password_banner_is_rejected_before_sending(self):
        for banner in [b"LOGIN: ", b"PassWord: "]:
            with self.subTest(banner=banner):
                sock = self.fake_connection([banner, socket.timeout()])
                with self.assertRaisesRegex(router.RouterLoginRequiredError, "direct shell on port 2323"):
                    router.fetch_sms_response()
                self.assertEqual(sock.sent, [])
                self.assertTrue(sock.closed)

    def test_completed_markers_without_json_raise_response_error(self):
        sock = self.fake_connection(
            self.transcript([COMMAND.encode(), MARKER.encode()])
        )
        with self.assertRaisesRegex(router.RouterResponseError, "complete router SMS response"):
            router.fetch_sms_response()
        self.assertTrue(sock.closed)

    def test_completed_markers_with_malformed_json_raise_response_error(self):
        sock = self.fake_connection(
            self.transcript(
                [COMMAND.encode(), b'{"code":200,"msg":"ok","data":', MARKER.encode()]
            )
        )
        with self.assertRaises(router.RouterResponseError):
            router.fetch_sms_response()
        self.assertTrue(sock.closed)

    def test_error_or_incomplete_envelopes_are_rejected(self):
        for payload in [
            {"code": 500, "msg": "ok", "data": []},
            {"code": 200, "msg": "error", "data": []},
            {"code": 200, "msg": "ok"},
            {"code": "200", "msg": "ok", "data": []},
        ]:
            with self.subTest(payload=payload):
                sock = self.fake_connection(self.transcript(self.completed_output(payload)))
                with self.assertRaises(router.RouterResponseError):
                    router.fetch_sms_response()
                self.assertTrue(sock.closed)

    def test_legacy_quirk_eof_before_command_output_is_reported_as_timeout(self):
        sock = self.fake_connection(self.transcript([b""]))
        with self.assertRaisesRegex(router.RouterTimeoutError, "SMS command to finish"):
            router.fetch_sms_response()
        self.assertTrue(sock.closed)

    def test_legacy_quirk_disconnect_mid_response_is_reported_as_timeout(self):
        sock = self.fake_connection(
            self.transcript([COMMAND.encode(), b'{"code":200,', b""])
        )
        with self.assertRaises(router.RouterTimeoutError):
            router.fetch_sms_response()
        self.assertTrue(sock.closed)

    def test_legacy_quirk_receive_oserror_is_labeled_connection_error(self):
        error = ConnectionResetError("synthetic reset")
        sock = self.fake_connection(self.transcript([error]))
        with self.assertRaisesRegex(router.RouterConnectionError, "Could not connect") as raised:
            router.fetch_sms_response()
        self.assertIs(raised.exception.__cause__, error)
        self.assertTrue(sock.closed)


class TelnetCharacterizationTests(OfflineCase):
    def test_will_and_do_are_refused_with_correct_option(self):
        sock = FakeSocket(self.clock)
        clean = router.handle_telnet_bytes(
            sock, b"before" + bytes([255, 251, 1, 255, 253, 3]) + b"after"
        )
        self.assertEqual(clean, b"beforeafter")
        self.assertEqual(sock.sent, [bytes([255, 254, 1]), bytes([255, 252, 3])])

    def test_wont_dont_and_other_two_byte_controls_are_ignored(self):
        sock = FakeSocket(self.clock)
        clean = router.handle_telnet_bytes(
            sock, bytes([255, 252, 1, 255, 254, 3, 255, 241]) + b"shell"
        )
        self.assertEqual(clean, b"shell")
        self.assertEqual(sock.sent, [])

    def test_escaped_iac_is_preserved_as_one_literal_byte(self):
        sock = FakeSocket(self.clock)
        self.assertEqual(router.handle_telnet_bytes(sock, b"a\xff\xffb"), b"a\xffb")
        self.assertEqual(sock.sent, [])

    def test_negotiation_reply_send_errors_are_swallowed(self):
        sock = FakeSocket(self.clock, send_error=OSError("synthetic send failure"))
        self.assertEqual(
            router.handle_telnet_bytes(sock, bytes([255, 251, 1]) + b"shell"), b"shell"
        )
        self.assertEqual(sock.sent, [bytes([255, 254, 1])])

    def test_legacy_quirk_fragmented_negotiation_loses_state_and_leaks_option(self):
        # Preserve the observed defect for Task 001; a future parser fix changes this test.
        for fragments, expected in [
            ([b"\xff", b"\xfb\x01shell"], b"\xfb\x01shell"),
            ([b"\xff\xfb", b"\x01shell"], b"\x01shell"),
        ]:
            with self.subTest(fragments=fragments):
                sock = FakeSocket(self.clock, [*fragments, socket.timeout()])
                self.assertEqual(
                    router.receive_some(sock), expected.decode("utf-8", errors="replace")
                )
                self.assertEqual(sock.sent, [])

    def test_banner_decode_replaces_invalid_utf8_instead_of_failing(self):
        sock = FakeSocket(self.clock, [b"shell\xfe\r\n", socket.timeout()])
        self.assertEqual(router.receive_some(sock), "shell\ufffd\r\n")


class CommandAndJsonCharacterizationTests(OfflineCase):
    def test_exact_ubus_command_uses_stringified_arg_and_crlf(self):
        self.assertEqual(router.build_sms_command(3, MARKER), COMMAND)
        self.assertEqual(
            router.build_sms_command(8, "SYNTHETIC_END"),
            'ubus -t 10 call cped cmd \'{"cmd":"sms.get.inboxdata",'
            '"arg":"{\\"StartPos\\":0,\\"ReadNum\\":8}"}\'; echo SYNTHETIC_END\r\n',
        )

    def test_json_with_noise_nested_objects_and_escaped_string_content(self):
        message = {"text": 'synthetic {braces}, quote " and slash \\', "nested": {"value": 1}}
        payload = {"code": 200, "msg": "ok", "data": [message]}
        output = "shell {broken}\r\n" + COMMAND + json.dumps(payload) + "\r\nnotice {bad}\r\n"
        objects = router.extract_valid_json_objects(output)
        self.assertIn(payload, objects)
        self.assertIn(message, objects)
        self.assertIn(message["nested"], objects)
        self.assertEqual(router.get_sms_response(output), payload)

    def test_stringified_data_is_preserved_without_decoding(self):
        stringified = json.dumps({"messages": [{"text": "synthetic {message}"}]})
        payload = {"code": 200, "msg": "ok", "data": stringified}
        self.assertEqual(router.get_sms_response("# " + json.dumps(payload) + "\r\n# "), payload)
        self.assertIsInstance(router.get_sms_response(json.dumps(payload))["data"], str)

    def test_last_successful_json_candidate_wins_over_later_error(self):
        first = {"code": 200, "msg": "ok", "data": ["first synthetic result"]}
        last = {"code": 200, "msg": "ok", "data": ["last synthetic result"]}
        error = {"code": 500, "msg": "error", "data": []}
        output = "\r\n".join(json.dumps(item) for item in [first, last, error])
        self.assertEqual(router.get_sms_response(output), last)

    def test_legacy_quirk_nested_success_envelope_can_override_outer_envelope(self):
        inner = {"code": 200, "msg": "ok", "data": []}
        outer = {"code": 200, "msg": "ok", "data": {"nested": inner}}
        self.assertEqual(router.get_sms_response(json.dumps(outer)), inner)

    def test_legacy_quirk_success_envelope_does_not_validate_data_shape(self):
        for data in [None, False, 17, {}, "synthetic unvalidated data"]:
            with self.subTest(data=data):
                payload = {"code": 200, "msg": "ok", "data": data}
                self.assertEqual(router.get_sms_response(json.dumps(payload)), payload)


if __name__ == "__main__":
    unittest.main()
