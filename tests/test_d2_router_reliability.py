"""Task 002 regressions using synthetic sockets, clocks and stop events only."""

import json
import socket
import threading
import traceback
from unittest.mock import patch

from test_d2_router import COMMAND, MARKER, PAYLOAD, FakeSocket, OfflineCase, router


class DeferredThread:
    """A connect worker scheduled explicitly by its test, never by the OS."""

    def __init__(self, target, args=(), kwargs=None, **options):
        self.target = target
        self.args = args
        self.kwargs = kwargs or {}
        self.daemon = options.get("daemon", False)

    def start(self):
        pass

    def run(self):
        self.target(*self.args, **self.kwargs)


class ControlledEvent:
    """Simulate the connect worker's completion event with controlled waits."""

    def __init__(self, clock, on_wait=None):
        self.clock = clock
        self.on_wait = on_wait
        self.flag = False
        self.waits = []

    def is_set(self):
        return self.flag

    def set(self):
        self.flag = True

    def wait(self, timeout):
        self.waits.append(timeout)
        self.clock.advance(timeout)
        if self.on_wait is not None:
            self.on_wait()
        return self.flag


class InteractiveSocket(FakeSocket):
    """Keep delayed shell phases separate while short idle polls repeat."""

    def __init__(self, clock, response=(), banner=(b"synthetic shell",), wakeup=(b"# ",)):
        super().__init__(clock)
        self.phase = "banner"
        self.phase_receives = {
            "banner": type(self.receives)(banner),
            "wakeup": type(self.receives)(wakeup),
            "response": type(self.receives)(response),
        }

    def sendall(self, data):
        super().sendall(data)
        if data == b"\r\n":
            self.phase = "wakeup"
        elif data.startswith(b"ubus -t 10 call cped cmd "):
            self.phase = "response"

    def recv(self, size):
        self.receives = self.phase_receives[self.phase]
        return super().recv(size)


class ConnectReliabilityTests(OfflineCase):
    def deferred_worker(self, completion):
        workers = []

        def thread(*args, **kwargs):
            worker = DeferredThread(*args, **kwargs)
            workers.append(worker)
            return worker

        self.stack.enter_context(patch.object(router.threading, "Thread", thread))
        self.stack.enter_context(patch.object(router.threading, "Event", return_value=completion))
        return workers

    def test_stalled_connect_expires_without_waiting_for_worker_and_closes_late_socket(self):
        sock = self.fake_connection([])
        completion = ControlledEvent(self.clock)
        workers = self.deferred_worker(completion)
        started = self.clock.now
        with self.assertRaises(router.RouterTimeoutError):
            router.fetch_sms_response(connect_timeout=0.2)
        self.connection.assert_not_called()
        self.assertEqual(len(workers), 1)
        self.assertTrue(workers[0].daemon)
        self.assertTrue(completion.waits)
        self.assertTrue(all(0 < wait <= 0.05 for wait in completion.waits))
        self.assertLess(self.clock.now - started, 0.35)
        workers[0].run()
        self.connection.assert_called_once_with(("192.168.1.1", 2323), timeout=0.2)
        self.assertTrue(sock.closed)
        self.assertEqual(sock.sent, [])

    def test_cancellation_during_stalled_connect_closes_late_socket(self):
        stop = threading.Event()
        sock = self.fake_connection([])
        completion = ControlledEvent(self.clock, on_wait=stop.set)
        workers = self.deferred_worker(completion)
        with self.assertRaises(router.RouterCancelledError):
            router.fetch_sms_response(connect_timeout=3.0, stop_event=stop)
        self.connection.assert_not_called()
        self.assertEqual(len(completion.waits), 1)
        self.assertLessEqual(completion.waits[0], 0.05)
        workers[0].run()
        self.assertTrue(sock.closed)
        self.assertEqual(sock.sent, [])

    def test_worker_completed_before_deadline_transfers_socket_to_fetch(self):
        sock = self.fake_connection(self.transcript(self.completed_output()))
        completion = ControlledEvent(self.clock)
        workers = self.deferred_worker(completion)
        completion.on_wait = lambda: workers[0].run()
        self.assertEqual(router.fetch_sms_response(), PAYLOAD)
        self.assertTrue(sock.closed)
        self.assertEqual(sock.sent, [b"\r\n", COMMAND.encode()])

    def test_worker_start_failure_is_sanitized_without_connection_attempt(self):
        sensitive = "SYNTHETIC_PRIVATE_THREAD_ERROR"

        class FailedThread(DeferredThread):
            def start(self):
                raise RuntimeError(sensitive)

        with patch.object(router.threading, "Thread", FailedThread):
            try:
                router.fetch_sms_response()
            except router.RouterConnectionError as exc:
                self.assertNotIn(sensitive, "".join(traceback.format_exception(exc)))
            else:
                self.fail("Expected sanitized worker startup failure")
        self.connection.assert_not_called()


class TelnetReliabilityTests(OfflineCase):
    def test_every_split_point_preserves_negotiation_and_escaped_iac(self):
        wire = b"first" + bytes([255, 251, 1, 255, 253, 3, 255, 255]) + b"last"
        for split in range(1, len(wire)):
            with self.subTest(split=split):
                sock = FakeSocket(self.clock, [wire[:split], wire[split:], socket.timeout()])
                self.assertEqual(router.receive_some(sock), "first\ufffdlast")
                self.assertEqual(sock.sent, [bytes([255, 254, 1]), bytes([255, 252, 3])])

    def test_bytewise_subnegotiation_discards_content_including_escaped_iac(self):
        # SB option payload IAC IAC payload IAC SE must stay out of shell/JSON text.
        wire = b"before" + bytes([255, 250, 24]) + b"private" + bytes([255, 255]) + b"value" + bytes([255, 240]) + b"after"
        sock = FakeSocket(self.clock, [bytes([value]) for value in wire] + [socket.timeout()])
        # A longer read window ensures bytewise synthetic data is drained.
        self.assertEqual(router.receive_some(sock, duration=3.0), "beforeafter")
        self.assertEqual(sock.sent, [])

    def test_decoder_state_is_shared_across_banner_and_wakeup_reads(self):
        sock = self.fake_connection(
            [
                b"shell\xff\xfb", socket.timeout(),
                b"\x01# ", socket.timeout(), *self.completed_output(),
            ]
        )
        self.assertEqual(router.fetch_sms_response(), PAYLOAD)
        self.assertEqual(sock.sent, [b"\r\n", b"\xff\xfe\x01", COMMAND.encode()])

    def test_decoder_state_is_shared_across_wakeup_and_response_reads(self):
        sock = self.fake_connection(
            [
                b"shell", socket.timeout(),
                b"# \xff\xfd", socket.timeout(),
                b"\x03" + self.completed_output()[0], *self.completed_output()[1:],
            ]
        )
        self.assertEqual(router.fetch_sms_response(), PAYLOAD)
        self.assertEqual(sock.sent, [b"\r\n", COMMAND.encode(), b"\xff\xfc\x03"])

    def test_decoder_state_does_not_leak_between_fetches(self):
        first = self.fake_connection(
            self.transcript([*self.completed_output()[:-1], MARKER.encode() + b"\r\n\xff"])
        )
        self.assertEqual(router.fetch_sms_response(), PAYLOAD)
        second = self.fake_connection(self.transcript(self.completed_output()))
        self.assertEqual(router.fetch_sms_response(), PAYLOAD)
        self.assertTrue(first.closed and second.closed)
        self.assertEqual(second.sent, [b"\r\n", COMMAND.encode()])


class CompletionReliabilityTests(OfflineCase):
    def test_negotiation_after_completion_marker_is_ignored_without_reply_writes(self):
        final_chunk = (
            json.dumps(PAYLOAD).encode() + b"\r\n" + MARKER.encode() + b"\r\n"
            + bytes([255, 251, 1]) * 20
        )
        sock = self.fake_connection(self.transcript([final_chunk]))
        self.assertEqual(router.fetch_sms_response(response_timeout=0.5), PAYLOAD)
        self.assertEqual(sock.sent, [b"\r\n", COMMAND.encode()])
        self.assertTrue(sock.closed)

    def test_json_after_completion_marker_in_same_chunk_cannot_override_response(self):
        trailing = {"code": 200, "msg": "ok", "data": ["synthetic trailing result"]}
        final_chunk = (
            json.dumps(PAYLOAD).encode() + b"\r\n" + MARKER.encode() + b"\r\n"
            + json.dumps(trailing).encode() + b"\r\n"
        )
        sock = self.fake_connection(self.transcript([final_chunk]))
        self.assertEqual(router.fetch_sms_response(), PAYLOAD)
        self.assertTrue(sock.closed)

    def test_marker_inside_command_or_json_does_not_finish_command(self):
        payload = {"code": 200, "msg": "ok", "data": [{"text": f"synthetic {MARKER}"}]}
        sock = self.fake_connection(
            self.transcript([COMMAND.encode(), json.dumps(payload).encode() + b"\r\n"])
        )
        with self.assertRaises(router.RouterTimeoutError):
            router.fetch_sms_response(response_timeout=0.75)
        self.assertTrue(sock.closed)

    def test_marker_as_substring_of_shell_line_does_not_finish_command(self):
        for line in [f"prefix{MARKER}\r\n", f"{MARKER}suffix\r\n", f" {MARKER}\r\n"]:
            with self.subTest(line=line):
                sock = self.fake_connection(
                    self.transcript([json.dumps(PAYLOAD).encode() + b"\r\n", line.encode()])
                )
                with self.assertRaises(router.RouterTimeoutError):
                    router.fetch_sms_response(response_timeout=0.5)
                self.assertTrue(sock.closed)

    def test_fragmented_marker_requires_terminating_line_break(self):
        sock = self.fake_connection(
            self.transcript(
                [json.dumps(PAYLOAD).encode() + b"\r\n", MARKER.encode(), socket.timeout(), b"\r", b"unread"]
            )
        )
        self.assertEqual(router.fetch_sms_response(response_timeout=2.0), PAYLOAD)
        self.assertEqual(list(sock.receives), [b"unread"])

    def test_unterminated_marker_then_eof_is_disconnect(self):
        sock = self.fake_connection(
            self.transcript([json.dumps(PAYLOAD).encode() + b"\r\n", MARKER.encode(), b""])
        )
        with self.assertRaises(router.RouterDisconnectedError):
            router.fetch_sms_response()
        self.assertTrue(sock.closed)

    def test_cr_lf_and_crlf_completion_lines_are_accepted(self):
        for newline in [b"\r", b"\n", b"\r\n"]:
            with self.subTest(newline=newline):
                sock = self.fake_connection(
                    self.transcript([json.dumps(PAYLOAD).encode() + newline, MARKER.encode() + newline])
                )
                self.assertEqual(router.fetch_sms_response(), PAYLOAD)
                self.assertTrue(sock.closed)


class EnvelopeReliabilityTests(OfflineCase):
    def test_malformed_balanced_outer_cannot_promote_nested_success(self):
        output = '{"code":500,"msg":"error","data":' + json.dumps(PAYLOAD) + ', BAD}'
        with self.assertRaises(router.RouterResponseError):
            router.get_sms_response(output)

    def test_unterminated_outer_cannot_promote_nested_success(self):
        output = '{"code":500,"msg":"error","data":' + json.dumps(PAYLOAD)
        with self.assertRaises(router.RouterResponseError):
            router.get_sms_response(output)

    def test_wrapped_outer_error_cannot_promote_nested_success(self):
        wrapped = {"result": {"code": 500, "msg": "error", "data": {"nested": PAYLOAD}}}
        with self.assertRaises(router.RouterResponseError):
            router.get_sms_response(json.dumps(wrapped))

    def test_wrapped_outer_success_is_selected_without_reinterpreting_its_data(self):
        inner = {"code": 200, "msg": "ok", "data": ["synthetic nested result"]}
        outer = {"code": 200, "msg": "ok", "data": {"nested": inner}}
        self.assertEqual(router.get_sms_response(json.dumps({"result": outer})), outer)

    def test_balanced_malformed_shell_noise_does_not_hide_later_valid_response(self):
        output = "shell {broken {also malformed}}\r\n" + json.dumps(PAYLOAD)
        self.assertEqual(router.get_sms_response(output), PAYLOAD)

    def test_nested_success_cannot_bypass_outer_error_or_incomplete_envelope(self):
        inner = {"code": 200, "msg": "ok", "data": []}
        for outer in [
            {"code": 500, "msg": "error", "data": {"nested": inner}},
            {"code": 200, "msg": "ok", "nested": inner},
            {"code": "200", "msg": "ok", "data": [inner]},
        ]:
            with self.subTest(outer=outer):
                with self.assertRaises(router.RouterResponseError):
                    router.get_sms_response(json.dumps(outer))

    def test_transparent_wrapper_still_allows_legacy_nested_success(self):
        wrapped = {"result": {"values": [{"code": 500, "msg": "error"}, PAYLOAD]}}
        self.assertEqual(router.get_sms_response(json.dumps(wrapped)), PAYLOAD)

    def test_top_level_success_takes_precedence_over_later_wrapped_success(self):
        inner = {"code": 200, "msg": "ok", "data": ["synthetic nested value"]}
        output = json.dumps(PAYLOAD) + "\r\n" + json.dumps({"result": inner})
        self.assertEqual(router.get_sms_response(output), PAYLOAD)

    def test_split_multibyte_utf8_in_payload_is_preserved(self):
        payload = {"code": 200, "msg": "ok", "data": [{"text": "synthetic café"}]}
        encoded = json.dumps(payload, ensure_ascii=False).encode() + b"\r\n"
        split = encoded.index("é".encode()) + 1
        sock = self.fake_connection(
            self.transcript([encoded[:split], encoded[split:], MARKER.encode() + b"\r\n"])
        )
        self.assertEqual(router.fetch_sms_response(), payload)
        self.assertTrue(sock.closed)


class DeadlineAndBoundReliabilityTests(OfflineCase):
    def test_each_receive_timeout_is_capped_by_remaining_monotonic_deadline(self):
        sock = FakeSocket(self.clock)
        started = self.clock.now
        with self.assertRaises(router.RouterTimeoutError):
            router.receive_until_marker_printed(sock, MARKER, timeout=0.08)
        waits = [event[1] for event in sock.events if event[0] == "settimeout"]
        self.assertTrue(waits)
        self.assertTrue(all(0 < timeout <= 0.08 for timeout in waits))
        self.assertLess(self.clock.now - started, 0.2)

    def test_deadline_expires_even_when_router_keeps_streaming_bytes(self):
        sock = self.fake_connection(self.transcript([b"noise"] * 100))
        with self.assertRaises(router.RouterTimeoutError):
            router.fetch_sms_response(response_timeout=0.15)
        self.assertTrue(sock.closed)
        self.assertTrue(sock.receives)

    def test_response_limit_counts_raw_negotiation_bytes_not_only_clean_text(self):
        flood = bytes([255, 252, 1]) * 100
        sock = self.fake_connection(self.transcript([flood]))
        with self.assertRaises(router.RouterResponseError):
            router.fetch_sms_response(max_response_bytes=256)
        self.assertTrue(sock.closed)

    def test_output_limit_applies_to_all_read_phases(self):
        flood = b"x" * 257
        for receives in [
            [flood],
            [b"banner", socket.timeout(), flood],
            self.transcript([flood]),
        ]:
            with self.subTest(phase=len(receives)):
                sock = self.fake_connection(receives)
                with self.assertRaises(router.RouterResponseError):
                    router.fetch_sms_response(max_response_bytes=256)
                self.assertTrue(sock.closed)

    def test_response_limit_accumulates_across_chunks(self):
        sock = self.fake_connection(self.transcript([b"a" * 100, b"b" * 100, b"c" * 100]))
        with self.assertRaises(router.RouterResponseError):
            router.fetch_sms_response(max_response_bytes=256)
        self.assertTrue(sock.closed)

    def test_send_timeout_is_typed_and_command_is_not_retried(self):
        sock = self.fake_connection(self.transcript([]))
        original_send = sock.sendall

        def send_with_timeout(data):
            original_send(data)
            if data == COMMAND.encode():
                self.clock.advance(sock.timeout)
                raise socket.timeout("synthetic partial send")

        sock.sendall = send_with_timeout
        with self.assertRaises(router.RouterTimeoutError):
            router.fetch_sms_response()
        self.assertEqual(sock.sent, [b"\r\n", COMMAND.encode()])
        self.assertTrue(sock.closed)

    def test_response_deadline_includes_json_parsing(self):
        completed = json.dumps(PAYLOAD).encode() + b"\r\n" + MARKER.encode() + b"\r\n"
        sock = self.fake_connection(self.transcript([completed]))
        raw_decode = json.JSONDecoder.raw_decode

        def delayed_decode(decoder, text, start=0):
            result = raw_decode(decoder, text, start)
            self.clock.advance(2.0)
            return result

        with patch.object(json.JSONDecoder, "raw_decode", autospec=True, side_effect=delayed_decode):
            with self.assertRaises(router.RouterTimeoutError):
                router.fetch_sms_response(response_timeout=1.0)
        self.assertTrue(sock.closed)

    def test_negotiation_reply_timeouts_share_response_deadline(self):
        sock = self.fake_connection(self.transcript([bytes([255, 251, 1]) * 20]))
        original_send = sock.sendall
        started = []

        def timed_send(data):
            original_send(data)
            if data == COMMAND.encode():
                started.append(self.clock.now)
            elif data == bytes([255, 254, 1]):
                self.clock.advance(sock.timeout)
                raise socket.timeout("synthetic negotiation write timeout")

        sock.sendall = timed_send
        with self.assertRaises(router.RouterTimeoutError):
            router.fetch_sms_response(response_timeout=0.3)
        replies = [value for value in sock.sent if value == bytes([255, 254, 1])]
        self.assertTrue(replies)
        self.assertLessEqual(len(replies), 2)
        self.assertLess(self.clock.now - started[0], 0.5)
        self.assertTrue(sock.closed)


class CancellationReliabilityTests(OfflineCase):
    def interactive_connection(self, response=(), banner=(b"synthetic shell",), wakeup=(b"# ",)):
        sock = InteractiveSocket(self.clock, response=response, banner=banner, wakeup=wakeup)
        self.connection.side_effect = None
        self.connection.return_value = sock
        return sock

    def stop_on_receive(self, event, result):
        def receive(sock):
            event.set()
            return result
        return receive

    def test_already_cancelled_request_does_not_connect(self):
        stop = threading.Event()
        stop.set()
        with self.assertRaises(router.RouterCancelledError):
            router.fetch_sms_response(stop_event=stop)
        self.connection.assert_not_called()

    def test_cancellation_immediately_after_connect_closes_socket_without_command(self):
        stop = threading.Event()
        sock = FakeSocket(self.clock)

        def connect(*args, **kwargs):
            stop.set()
            return sock

        self.connection.side_effect = connect
        with self.assertRaises(router.RouterCancelledError):
            router.fetch_sms_response(stop_event=stop)
        self.assertTrue(sock.closed)
        self.assertEqual(sock.sent, [])

    def test_cancellation_during_banner_stops_before_wakeup(self):
        stop = threading.Event()
        sock = self.fake_connection([self.stop_on_receive(stop, b"shell")])
        with self.assertRaises(router.RouterCancelledError):
            router.fetch_sms_response(stop_event=stop)
        self.assertEqual(sock.sent, [])
        self.assertTrue(sock.closed)

    def test_cancellation_during_wakeup_stops_before_command(self):
        stop = threading.Event()
        sock = self.interactive_connection(wakeup=[self.stop_on_receive(stop, b"# ")])
        with self.assertRaises(router.RouterCancelledError):
            router.fetch_sms_response(stop_event=stop)
        self.assertEqual(sock.sent, [b"\r\n"])
        self.assertTrue(sock.closed)

    def test_cancellation_during_response_timeout_has_bounded_wait(self):
        stop = threading.Event()
        sock = self.interactive_connection(response=[self.stop_on_receive(stop, socket.timeout())])
        with self.assertRaises(router.RouterCancelledError):
            router.fetch_sms_response(stop_event=stop)
        waits = [timeout for operation, timeout in sock.io_timeouts]
        self.assertTrue(waits)
        self.assertTrue(all(0 < timeout <= 0.1 for timeout in waits))
        self.assertTrue(sock.closed)

    def test_cancellation_with_completed_response_prevents_stale_success(self):
        stop = threading.Event()
        completed = json.dumps(PAYLOAD).encode() + b"\r\n" + MARKER.encode() + b"\r\n"
        sock = self.interactive_connection(response=[self.stop_on_receive(stop, completed)])
        with self.assertRaises(router.RouterCancelledError):
            router.fetch_sms_response(stop_event=stop)
        self.assertTrue(sock.closed)

    def test_cancellation_during_json_parsing_closes_socket(self):
        stop = threading.Event()
        completed = json.dumps(PAYLOAD).encode() + b"\r\n" + MARKER.encode() + b"\r\n"
        sock = self.interactive_connection(response=[completed])
        raw_decode = json.JSONDecoder.raw_decode

        def cancelled_decode(decoder, text, start=0):
            result = raw_decode(decoder, text, start)
            stop.set()
            return result

        with patch.object(json.JSONDecoder, "raw_decode", autospec=True, side_effect=cancelled_decode):
            with self.assertRaises(router.RouterCancelledError):
                router.fetch_sms_response(stop_event=stop)
        self.assertTrue(sock.closed)

    def test_short_banner_poll_timeout_still_allows_delayed_login_bytes(self):
        stop = threading.Event()
        sock = FakeSocket(self.clock, [socket.timeout(), b"LOGIN: "])
        self.assertEqual(router.receive_some(sock, duration=0.7, stop_event=stop), "LOGIN: ")
        self.assertTrue(all(0 < timeout <= 0.1 for operation, timeout in sock.io_timeouts))

    def test_cancellation_is_checked_during_repeated_banner_idle_polls(self):
        stop = threading.Event()
        sock = FakeSocket(
            self.clock, [socket.timeout(), self.stop_on_receive(stop, socket.timeout())]
        )
        with self.assertRaises(router.RouterCancelledError):
            router.receive_some(sock, duration=0.7, stop_event=stop)
        self.assertEqual(len(sock.io_timeouts), 2)
        self.assertTrue(all(0 < timeout <= 0.1 for operation, timeout in sock.io_timeouts))

    def test_cancellable_fetch_keeps_shell_read_phases_and_detects_delayed_login(self):
        stop = threading.Event()
        sock = self.interactive_connection(
            banner=[socket.timeout(), b"LOGIN: "], response=self.completed_output()
        )
        with self.assertRaises(router.RouterLoginRequiredError):
            router.fetch_sms_response(stop_event=stop)
        self.assertEqual(sock.sent, [])
        self.assertTrue(sock.closed)

    def test_cancellable_fetch_succeeds_after_repeated_short_idle_polls(self):
        stop = threading.Event()
        sock = self.interactive_connection(response=self.completed_output())
        self.assertEqual(router.fetch_sms_response(stop_event=stop), PAYLOAD)
        self.assertEqual(sock.sent, [b"\r\n", COMMAND.encode()])
        self.assertTrue(sock.closed)

    def test_cancellation_during_negotiation_prevents_further_reply_writes(self):
        for fail_reply in [False, True]:
            with self.subTest(fail_reply=fail_reply):
                stop = threading.Event()
                sock = self.fake_connection([bytes([255, 251, 1, 255, 253, 3]) + b"shell"])
                original_send = sock.sendall

                def cancelled_send(data):
                    original_send(data)
                    stop.set()
                    if fail_reply:
                        raise socket.timeout("synthetic negotiation write timeout")

                sock.sendall = cancelled_send
                with self.assertRaises(router.RouterCancelledError):
                    router.fetch_sms_response(stop_event=stop)
                self.assertEqual(sock.sent, [bytes([255, 254, 1])])
                self.assertTrue(sock.closed)


class PrivacyReliabilityTests(OfflineCase):
    def test_formatted_traceback_omits_raw_io_error_values_in_every_phase(self):
        # Noncredential labels stand in for secrets; no real identifiers or OTPs.
        sensitive = "SYNTHETIC_PRIVATE_VALUE_MUST_BE_OMITTED"
        for phase in ["connect", "banner", "wakeup", "response", "send"]:
            with self.subTest(phase=phase):
                error = OSError(sensitive)
                sock = None
                if phase == "connect":
                    self.connection.side_effect = error
                elif phase == "banner":
                    sock = self.fake_connection([error])
                elif phase == "wakeup":
                    sock = self.fake_connection([b"banner", socket.timeout(), error])
                elif phase == "response":
                    sock = self.fake_connection(self.transcript([error]))
                else:
                    sock = self.fake_connection([b"banner", socket.timeout()])
                    sock.send_error = error
                try:
                    router.fetch_sms_response()
                except router.RouterError as exc:
                    rendered = "".join(traceback.format_exception(exc))
                    self.assertNotIn(sensitive, str(exc))
                    self.assertNotIn(sensitive, rendered)
                else:
                    self.fail("Expected sanitized transport failure")
                if sock is not None:
                    self.assertTrue(sock.closed)

    def test_response_errors_omit_payload_and_logging_is_silent(self):
        sensitive = "SYNTHETIC_PRIVATE_SMS_MUST_BE_OMITTED"
        sock = self.fake_connection(
            self.transcript([COMMAND.encode(), sensitive.encode() + b"\r\n", MARKER.encode() + b"\r\n"])
        )
        with patch("builtins.print") as printed, self.assertNoLogs(level="DEBUG"):
            try:
                router.fetch_sms_response()
            except router.RouterResponseError as exc:
                self.assertNotIn(sensitive, "".join(traceback.format_exception(exc)))
            else:
                self.fail("Expected sanitized response failure")
        printed.assert_not_called()
        self.assertTrue(sock.closed)

    def test_json_value_error_is_rejected_without_disclosing_decoder_details(self):
        sensitive = "SYNTHETIC_PRIVATE_DECODER_ERROR"
        sock = self.fake_connection(self.transcript(self.completed_output()))
        # CPython can raise ValueError for oversized integer literals; simulate
        # that behavior portably without relying on a host digit-limit setting.
        with patch.object(json.JSONDecoder, "raw_decode", side_effect=ValueError(sensitive)):
            try:
                router.fetch_sms_response()
            except router.RouterResponseError as exc:
                self.assertNotIn(sensitive, "".join(traceback.format_exception(exc)))
            else:
                self.fail("Expected sanitized malformed JSON failure")
        self.assertTrue(sock.closed)
