"""Synthetic HTTPS/session tests; no browser, real sockets, or credentials.

Login envelopes are synthetic instances of the source-verified firmware shape.
Private token installation isolates read-only tests from authentication tests.
"""

from collections import deque
import errno
import json
import socket
import ssl
from threading import Event
import traceback
import unittest
from unittest.mock import Mock, patch

from sim_manager.devices.d2 import errors, session
from sim_manager.devices.d2.status import D2StatusClient, ENDPOINTS
from sim_manager.models import IssueCode


PRIVATE_PASSWORD = "SYNTHETIC_PASSWORD_ONLY"
PRIVATE_TOKEN = "SYNTHETIC_SESSION_ONLY"
PRIVATE_USERNAME = "SYNTHETIC_USERNAME_ONLY"
PATH = next(iter(ENDPOINTS.values()))


class Clock:
    def __init__(self):
        self.value = 10.0

    def __call__(self):
        return self.value


class FakeSocket:
    def __init__(self, incoming=(), *, connection=0, handshake=(), send_actions=()):
        self.incoming = deque(incoming)
        self.handshakes = deque(handshake)
        self.send_actions = deque(send_actions)
        self.connection = connection
        self.sent = bytearray()
        self.closed = False
        self.blocking = None
        self.address = None

    @staticmethod
    def action(value):
        if isinstance(value, BaseException):
            raise value
        return value() if callable(value) else value

    def setblocking(self, flag):
        self.blocking = flag

    def connect_ex(self, address):
        self.address = address
        return self.action(self.connection)

    def getsockopt(self, *_args):
        return 0

    def do_handshake(self):
        if self.handshakes:
            self.action(self.handshakes.popleft())

    def send(self, data):
        result = self.action(self.send_actions.popleft()) if self.send_actions else len(data)
        count = min(result, len(data))
        self.sent.extend(data[:count])
        return count

    def recv(self, limit):
        if not self.incoming:
            return b""
        data = self.action(self.incoming.popleft())
        if len(data) > limit:
            self.incoming.appendleft(data[limit:])
            data = data[:limit]
        return data

    def close(self):
        self.closed = True


class FakeContext:
    verify_mode = ssl.CERT_REQUIRED
    check_hostname = True

    def __init__(self, failure=None):
        self.failure = failure
        self.wrapped = []

    def wrap_socket(self, sock, **options):
        self.wrapped.append(options)
        if self.failure:
            raise self.failure
        return sock


def http(body=b'{"code":200,"data":{}}', *, status=200, extra=b"", framing=True):
    length = b"Content-Length: " + str(len(body)).encode() + b"\r\n" if framing else b""
    return b"HTTP/1.1 " + str(status).encode() + b" Synthetic\r\n" + length + extra + b"\r\n" + body


def login_result(token=PRIVATE_TOKEN):
    return session._HttpResult(200, json.dumps({"code": 200, "data": {"Authorization": token}}).encode())


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch("socket.socket", side_effect=AssertionError("Real sockets forbidden")).start()
        patch("socket.create_connection", side_effect=AssertionError("Real connections forbidden")).start()
        self.clock = Clock()

    def transport(self, sock, context=None):
        return session._HttpsTransport(
            "https://192.168.1.1", clock=self.clock,
            socket_factory=lambda *_args: sock,
            ssl_context=FakeContext() if context is None else context,
        )

    def exchange(self, transport, *, deadline=30, stop_event=None, session_stop=None, max_bytes=1024):
        return transport.exchange(
            "GET", PATH, body=b"", authorization=PRIVATE_TOKEN,
            deadline=deadline, stop_event=stop_event,
            session_stop=Event() if session_stop is None else session_stop,
            max_bytes=max_bytes,
        )

    def authenticated(self, transport):
        result = session.D2Session(_transport=transport, _clock=self.clock)
        # Deliberately synthetic: never read a browser token or expose a setter.
        result._token = PRIVATE_TOKEN
        return result

    def read(self, client, **options):
        return client.read_json(PATH, deadline=30, stop_event=None, max_bytes=1024, **options)


class TransportTests(OfflineCase):
    def test_nonblocking_https_get_has_private_header_and_no_cookie(self):
        sock = FakeSocket([http()])
        context = FakeContext()
        result = self.exchange(self.transport(sock, context))
        self.assertEqual(result.status, 200)
        self.assertFalse(sock.blocking)
        self.assertEqual(sock.address, ("192.168.1.1", 443))
        self.assertEqual(context.wrapped, [{"server_hostname": "192.168.1.1", "do_handshake_on_connect": False}])
        self.assertIn(b"Authorization: " + PRIVATE_TOKEN.encode(), sock.sent)
        self.assertNotIn(b"Cookie:", sock.sent)
        self.assertTrue(sock.closed)
        self.assertNotIn(PRIVATE_TOKEN, repr(result))

    def test_fragmented_headers_body_and_partial_sends(self):
        response = http()
        sock = FakeSocket([response[:8], response[8:25], response[25:-3], response[-3:]], send_actions=[2, 3])
        result = self.exchange(self.transport(sock))
        self.assertEqual(json.loads(result.body)["code"], 200)
        self.assertTrue(bytes(sock.sent).endswith(b"\r\n\r\n"))

    def test_eof_delimited_body(self):
        sock = FakeSocket([http(framing=False)])
        self.assertEqual(self.exchange(self.transport(sock)).status, 200)

    def test_chunked_body(self):
        sock = FakeSocket([http(b'7\r\n{"a":1}\r\n0\r\n\r\n', extra=b"Transfer-Encoding: chunked\r\n", framing=False)])
        self.assertEqual(self.exchange(self.transport(sock)).body, b'{"a":1}')

    def test_redirect_is_rejected_and_connection_closed(self):
        sock = FakeSocket([http(status=302, extra=b"Location: https://example.invalid/\r\n")])
        with self.assertRaises(errors.D2ConnectionError):
            self.exchange(self.transport(sock))
        self.assertTrue(sock.closed)

    def test_auth_failure_ignores_hostile_or_slow_response_body(self):
        for status in (401, 403):
            response = b"HTTP/1.1 " + str(status).encode() + b" Denied\r\nContent-Length: 999999999\r\n\r\n"
            sock = FakeSocket([response, AssertionError("Must not wait for auth failure body")])
            result = self.exchange(self.transport(sock), max_bytes=4)
            self.assertEqual(result.status, status)
            self.assertEqual(result.body, b"")
            self.assertTrue(sock.closed)

    def test_unreachable_connect_is_closed(self):
        sock = FakeSocket(connection=errno.ECONNREFUSED)
        with self.assertRaises(errors.D2Unreachable):
            self.exchange(self.transport(sock))
        self.assertTrue(sock.closed)

    def test_connect_exception_is_sanitized(self):
        sock = FakeSocket(connection=OSError(PRIVATE_PASSWORD))
        try:
            self.exchange(self.transport(sock))
        except errors.D2Unreachable as exc:
            self.assertNotIn(PRIVATE_PASSWORD, "".join(traceback.format_exception(exc)))
            self.assertIsNone(exc.__cause__)
            self.assertIsNone(exc.__context__)
        else:
            self.fail("Expected safe connection failure")

    def test_wrap_failure_closes_original_socket(self):
        sock = FakeSocket()
        with self.assertRaises(errors.D2ConnectionError):
            self.exchange(self.transport(sock, FakeContext(ssl.SSLError(PRIVATE_TOKEN))))
        self.assertTrue(sock.closed)

    def test_tls_handshake_cancellation_closes_socket(self):
        stop = Event()
        sock = FakeSocket(handshake=[ssl.SSLWantReadError()])
        def wait(*_args):
            stop.set()
            return [], [], []
        with patch("select.select", side_effect=wait):
            with self.assertRaises(errors.D2Cancelled):
                self.exchange(self.transport(sock), stop_event=stop)
        self.assertTrue(sock.closed)

    def test_pending_connect_timeout_polls_shared_deadline(self):
        sock = FakeSocket(connection=errno.EINPROGRESS)
        delays = []
        def wait(_reads, _writes, _errors, delay):
            delays.append(delay)
            self.clock.value += delay
            return [], [], []
        with patch("select.select", side_effect=wait):
            with self.assertRaises(errors.D2Timeout):
                self.exchange(self.transport(sock), deadline=10.14)
        self.assertLessEqual(max(delays), 0.05)
        self.assertTrue(sock.closed)

    def test_pending_connect_cancellation(self):
        sock = FakeSocket(connection=errno.EINPROGRESS)
        stop = Event()
        def wait(*_args):
            stop.set()
            return [], [], []
        with patch("select.select", side_effect=wait):
            with self.assertRaises(errors.D2Cancelled):
                self.exchange(self.transport(sock), stop_event=stop)
        self.assertTrue(sock.closed)

    def test_read_cancellation(self):
        stop = Event()
        sock = FakeSocket([ssl.SSLWantReadError()])
        def wait(*_args):
            stop.set()
            return [], [], []
        with patch("select.select", side_effect=wait):
            with self.assertRaises(errors.D2Cancelled):
                self.exchange(self.transport(sock), stop_event=stop)
        self.assertTrue(sock.closed)

    def test_send_cancellation(self):
        stop = Event()
        sock = FakeSocket(send_actions=[ssl.SSLWantWriteError()])
        def wait(*_args):
            stop.set()
            return [], [], []
        with patch("select.select", side_effect=wait):
            with self.assertRaises(errors.D2Cancelled):
                self.exchange(self.transport(sock), stop_event=stop)
        self.assertTrue(sock.closed)

    def test_late_response_is_discarded(self):
        def late():
            self.clock.value = 31
            return http()
        sock = FakeSocket([late])
        with self.assertRaises(errors.D2Timeout):
            self.exchange(self.transport(sock))
        self.assertTrue(sock.closed)

    def test_body_caps_all_three_framings(self):
        bodies = [http(b"12345"), http(b"12345", framing=False),
                  http(b"5\r\n12345\r\n0\r\n\r\n", extra=b"Transfer-Encoding: chunked\r\n", framing=False)]
        for response in bodies:
            with self.subTest(response=response[:16]):
                sock = FakeSocket([response])
                with self.assertRaises(errors.D2ResponseTooLarge):
                    self.exchange(self.transport(sock), max_bytes=4)
                self.assertTrue(sock.closed)

    def test_oversized_headers_are_rejected(self):
        sock = FakeSocket([b"HTTP/1.1 200 OK\r\nX: " + b"a" * (16 * 1024 + 1)])
        with self.assertRaises(errors.D2MalformedResponse):
            self.exchange(self.transport(sock))

    def test_invalid_headers_and_framing_are_rejected(self):
        responses = [b"nonsense\r\n\r\n", http(extra=b"Content-Length: 2\r\n"),
                     http(extra=b"Transfer-Encoding: chunked\r\n"),
                     http(extra=b"Content-Encoding: gzip\r\n"),
                     http(b"x", extra=b"Transfer-Encoding: unsupported\r\n", framing=False)]
        for response in responses:
            with self.subTest(response=response[:16]):
                with self.assertRaises(errors.D2MalformedResponse):
                    self.exchange(self.transport(FakeSocket([response])))

    def test_truncated_body_is_connection_problem(self):
        sock = FakeSocket([b"HTTP/1.1 200 OK\r\nContent-Length: 12\r\n\r\nx"])
        with self.assertRaises(errors.D2ConnectionError):
            self.exchange(self.transport(sock))

    def test_disabled_certificate_verification_rejected(self):
        context = FakeContext()
        context.verify_mode = ssl.CERT_NONE
        with self.assertRaises(ValueError):
            self.transport(FakeSocket(), context)

    def test_explicit_certificate_context_uses_only_its_anchor(self):
        context = Mock(verify_mode=ssl.CERT_REQUIRED)
        with patch("ssl.SSLContext", return_value=context) as create:
            with patch("ssl.create_default_context", side_effect=AssertionError("Unrelated trust roots forbidden")):
                session._HttpsTransport("https://192.168.1.1", trusted_certificate="SYNTHETIC_PUBLIC_CERT")
        create.assert_called_once_with(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations.assert_called_once_with(cadata="SYNTHETIC_PUBLIC_CERT")
        self.assertNotEqual(context.check_hostname, False)

    def test_bundled_router_certificate_keeps_verification_and_hostname_checks(self):
        client = session.D2Session()
        context = client._transport._context
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.cert_store_stats()["x509"], 1)

    def test_default_context_keeps_hostname_verification(self):
        context = FakeContext()
        with patch("ssl.create_default_context", return_value=context):
            transport = session._HttpsTransport("https://192.168.1.1")
        self.assertTrue(transport._context.check_hostname)

    def test_only_verified_status_gets_and_login_post_are_allowed(self):
        transport = self.transport(FakeSocket())
        for method, path, body in [("POST", PATH, b"{}"), ("GET", "/web/set", b""),
                                   ("GET", PATH, b"{}"), ("GET", session._LOGIN_PATH, b""),
                                   ("POST", "/web/v1/user/logout", b"{}")]:
            with self.assertRaises(ValueError):
                transport.exchange(method, path, body=body, authorization=None,
                                   deadline=30, stop_event=None, session_stop=Event(), max_bytes=1024)

    def test_login_post_is_exact_json_utf8_without_authorization_or_cookie(self):
        body = json.dumps({"username": PRIVATE_USERNAME, "password": "synthetic\u2603"}, ensure_ascii=False).encode()
        sock = FakeSocket([http(login_result().body)])
        result = self.transport(sock).exchange(
            "POST", "/web/v1/user/login", body=body, authorization=None,
            deadline=30, stop_event=None, session_stop=Event(), max_bytes=64 * 1024,
        )
        self.assertEqual(result.status, 200)
        self.assertTrue(sock.sent.startswith(b"POST /web/v1/user/login HTTP/1.1\r\n"))
        self.assertIn(b"Content-Type: application/json;charset=utf-8\r\n", sock.sent)
        self.assertTrue(sock.sent.endswith(body))
        self.assertNotIn(b"Authorization:", sock.sent)
        self.assertNotIn(b"Cookie:", sock.sent)
        self.assertTrue(sock.closed)

    def test_authorization_is_bounded_and_safe_for_http_header(self):
        for token in ["", " ", "x\r\nCookie: private", "x\x00", "nonascii\u2603", "x" * 4097, 123]:
            sock = FakeSocket()
            with self.assertRaises(errors.D2ConnectionError):
                self.transport(sock).exchange(
                    "GET", PATH, body=b"", authorization=token,
                    deadline=30, stop_event=None, session_stop=Event(), max_bytes=1024,
                )
            self.assertIsNone(sock.address)


class SessionTests(OfflineCase):
    def test_no_session_requires_authentication_without_io(self):
        transport = Mock()
        client = session.D2Session(_transport=transport)
        with self.assertRaises(errors.D2AuthenticationRequired):
            client.read_json(PATH, deadline=session.time.monotonic() + 30, stop_event=None, max_bytes=1024)
        transport.exchange.assert_not_called()

    def test_successful_login_owns_verbatim_private_token(self):
        transport = Mock()
        transport.exchange.return_value = login_result()
        client = session.D2Session(_transport=transport, _clock=self.clock)
        self.assertIsNone(client.authenticate(PRIVATE_PASSWORD, username=PRIVATE_USERNAME))
        self.assertTrue(client.is_authenticated())
        args, options = transport.exchange.call_args
        self.assertEqual(args, ("POST", "/web/v1/user/login"))
        self.assertEqual(json.loads(options["body"]), {"username": PRIVATE_USERNAME, "password": PRIVATE_PASSWORD})
        self.assertIsNone(options["authorization"])
        self.assertEqual(options["max_bytes"], 64 * 1024)
        self.assertEqual(options["deadline"], 30)
        self.assertNotIn(PRIVATE_PASSWORD, repr(vars(client)))
        transport.exchange.return_value = session._HttpResult(200, b'{"code":200}')
        self.read(client)
        self.assertEqual(transport.exchange.call_args.kwargs["authorization"], PRIVATE_TOKEN)

    def test_login_preserves_exact_username_and_password_text(self):
        transport = Mock()
        transport.exchange.return_value = login_result()
        client = session.D2Session(_transport=transport, _clock=self.clock)
        client.authenticate(" synthetic\u2603 ", username=" synthetic user ")
        body = transport.exchange.call_args.kwargs["body"]
        self.assertEqual(json.loads(body), {"username": " synthetic user ", "password": " synthetic\u2603 "})
        self.assertIn("\u2603".encode(), body)

    def test_rejected_authentication_is_bounded_and_discards_old_session(self):
        responses = [session._HttpResult(401, b""), session._HttpResult(403, b""),
                     session._HttpResult(200, b'{"code":401,"msg":"SYNTHETIC_PRIVATE"}'),
                     session._HttpResult(200, b'{"code":499,"msg":"SYNTHETIC_PRIVATE"}')]
        # 499 is an explicitly synthetic arbitrary rejection code; no actual
        # wrong-password response code has been claimed from hardware.
        for response in responses:
            transport = Mock()
            transport.exchange.return_value = response
            client = self.authenticated(transport)
            with self.assertRaises(errors.D2AuthenticationRejected) as caught:
                client.authenticate(PRIVATE_PASSWORD, username=PRIVATE_USERNAME)
            self.assertFalse(client.is_authenticated())
            self.assertEqual(transport.exchange.call_count, 1)
            self.assertIsNone(caught.exception.__context__)

    def test_malformed_login_responses_are_private(self):
        bodies = [PRIVATE_PASSWORD.encode(), b"[]", b'{"code":"200"}',
                  b'{"code":true}', b'{"code":200}', b'{"code":200,"data":null}']
        for body in bodies:
            transport = Mock()
            transport.exchange.return_value = session._HttpResult(200, body)
            client = self.authenticated(transport)
            with self.assertRaises(errors.D2MalformedAuthentication) as caught:
                client.authenticate(PRIVATE_PASSWORD, username=PRIVATE_USERNAME)
            self.assertFalse(client.is_authenticated())
            self.assertIsNone(caught.exception.__context__)
            self.assertNotIn(PRIVATE_PASSWORD, str(caught.exception))

    def test_missing_or_unsafe_login_tokens_are_rejected_before_storage(self):
        responses = [session._HttpResult(200, b'{"code":200,"data":{}}')]
        responses.extend(login_result(value) for value in [None, 123, "", " ", "x\r\nCookie: value", "x\x00", "\u2603", "x" * 4097])
        for response in responses:
            transport = Mock()
            transport.exchange.return_value = response
            client = session.D2Session(_transport=transport, _clock=self.clock)
            with self.assertRaises(errors.D2MissingSessionToken):
                client.authenticate(PRIVATE_PASSWORD, username=PRIVATE_USERNAME)
            self.assertFalse(client.is_authenticated())

    def test_login_timeout_unreachable_connection_and_cancellation_are_safe(self):
        for error_type in [errors.D2Timeout, errors.D2Unreachable, errors.D2ConnectionError, errors.D2Cancelled]:
            transport = Mock()
            transport.exchange.side_effect = error_type(PRIVATE_PASSWORD)
            client = self.authenticated(transport)
            with self.assertRaises(error_type) as caught:
                client.authenticate(PRIVATE_PASSWORD, username=PRIVATE_USERNAME)
            self.assertFalse(client.is_authenticated())
            self.assertEqual(transport.exchange.call_count, 1)
            self.assertIsNone(caught.exception.__context__)
            self.assertNotIn(PRIVATE_PASSWORD, repr(caught.exception))

    def test_unknown_login_transport_failure_cannot_retain_secrets(self):
        transport = Mock()
        transport.exchange.side_effect = RuntimeError(PRIVATE_PASSWORD + PRIVATE_TOKEN)
        client = self.authenticated(transport)
        with self.assertRaises(errors.D2MalformedAuthentication) as caught:
            client.authenticate(PRIVATE_PASSWORD, username=PRIVATE_USERNAME)
        self.assertIsNone(caught.exception.__context__)
        self.assertNotIn(PRIVATE_PASSWORD, "".join(traceback.format_exception(caught.exception)))
        current = caught.exception.__traceback__
        while current is not None:
            frame = current.tb_frame
            if frame.f_globals.get("__name__") == session.__name__ and frame.f_code.co_name == "authenticate":
                for key in ("password", "username"):
                    self.assertEqual(frame.f_locals[key], "")
                for key in ("response", "payload", "data", "token"):
                    self.assertIsNone(frame.f_locals[key])
                self.assertEqual(frame.f_locals["body"], b"")
            current = current.tb_next

    def test_expired_session_can_be_reauthenticated_once_explicitly(self):
        transport = Mock()
        transport.exchange.side_effect = [login_result(), session._HttpResult(401, b""),
                                          login_result("SECOND_SYNTHETIC_TOKEN"),
                                          session._HttpResult(200, b'{"code":200}')]
        client = session.D2Session(_transport=transport, _clock=self.clock)
        client.authenticate(PRIVATE_PASSWORD, username=PRIVATE_USERNAME)
        with self.assertRaises(errors.D2AuthenticationRequired):
            self.read(client)
        self.assertFalse(client.is_authenticated())
        client.authenticate(PRIVATE_PASSWORD, username=PRIVATE_USERNAME)
        self.read(client)
        self.assertTrue(client.is_authenticated())
        self.assertEqual(transport.exchange.call_args.kwargs["authorization"], "SECOND_SYNTHETIC_TOKEN")
        self.assertEqual([call.args[0] for call in transport.exchange.call_args_list], ["POST", "GET", "POST", "GET"])

    def test_late_login_response_cannot_install_token(self):
        for action in ("cancel", "timeout", "invalidate", "close"):
            self.clock.value = 10
            transport = Mock()
            client = session.D2Session(_transport=transport, _clock=self.clock)
            stop = Event()
            def late(*_args, **_options):
                if action == "cancel":
                    stop.set()
                elif action == "timeout":
                    self.clock.value = 31
                elif action == "invalidate":
                    client.invalidate()
                else:
                    client.close()
                return login_result()
            transport.exchange.side_effect = late
            expected = errors.D2Timeout if action == "timeout" else errors.D2Cancelled
            with self.assertRaises(expected):
                client.authenticate(PRIVATE_PASSWORD, username=PRIVATE_USERNAME, stop_event=stop)
            self.assertFalse(client.is_authenticated())

    def test_opaque_reprs(self):
        client = self.authenticated(Mock())
        self.assertNotIn(PRIVATE_TOKEN, repr(client))
        self.assertNotIn(PRIVATE_TOKEN, str(client))
        self.assertNotIn("192.168", repr(client))

    def test_origin_is_normalized_and_unsafe_origins_rejected(self):
        self.assertEqual(session.D2Session("https://192.168.1.1/", _transport=Mock()).origin, "https://192.168.1.1")
        for origin in ["http://192.168.1.1", "https://example.com", "https://8.8.8.8",
                       "https://192.168.1.1/path", "https://user:secret@192.168.1.1", "https://192.168.1.1?token=secret"]:
            with self.subTest(origin=origin):
                with self.assertRaises(ValueError) as caught:
                    session.D2Session(origin, _transport=Mock())
                self.assertNotIn(origin, str(caught.exception))

    def test_status_response_stays_inside_private_device_boundary(self):
        transport = Mock()
        transport.exchange.return_value = session._HttpResult(200, b'{"code":200,"data":{}}')
        client = self.authenticated(transport)
        result = self.read(client)
        self.assertEqual(result.payload["code"], 200)
        self.assertEqual(transport.exchange.call_args.kwargs["authorization"], PRIVATE_TOKEN)
        self.assertEqual(transport.exchange.call_args.kwargs["deadline"], 30)
        self.assertNotIn(PRIVATE_TOKEN, repr(result))

    def test_http_and_envelope_auth_failures_invalidate(self):
        for status, body in [(401, b""), (403, b""), (200, b'{"code":401}'), (200, b'{"code":403}')]:
            transport = Mock()
            transport.exchange.return_value = session._HttpResult(status, body)
            client = self.authenticated(transport)
            with self.assertRaises(errors.D2AuthenticationRequired):
                self.read(client)
            self.assertFalse(client.is_authenticated())

    def test_status_expiry_stops_aggregate_requests(self):
        transport = Mock()
        transport.exchange.return_value = session._HttpResult(401, b"")
        client = self.authenticated(transport)
        state = D2StatusClient(client, clock=self.clock).get_device_state()
        self.assertTrue(all(issue.code is IssueCode.AUTHENTICATION_REQUIRED for issue in state.errors))
        self.assertEqual(transport.exchange.call_count, 1)
        self.assertFalse(client.is_authenticated())

    def test_partial_status_failure_retains_usable_snapshot(self):
        transport = Mock()
        transport.exchange.side_effect = [errors.D2ConnectionError()] + [session._HttpResult(200, b'{"code":200,"data":{}}')] * 6
        client = self.authenticated(transport)
        state = D2StatusClient(client, clock=self.clock).get_device_state()
        self.assertEqual(transport.exchange.call_count, 7)
        self.assertEqual(len(state.errors), 1)
        self.assertTrue(client.is_authenticated())

    def test_malformed_payload_is_sanitized(self):
        transport = Mock()
        transport.exchange.return_value = session._HttpResult(200, PRIVATE_TOKEN.encode())
        with self.assertRaises(errors.D2MalformedResponse) as caught:
            self.read(self.authenticated(transport))
        self.assertNotIn(PRIVATE_TOKEN, "".join(traceback.format_exception(caught.exception)))
        self.assertIsNone(caught.exception.__context__)

    def test_status_errors_do_not_retain_private_transport_or_parser_frames(self):
        transport = Mock()
        transport.exchange.return_value = session._HttpResult(200, PRIVATE_TOKEN.encode())
        client = self.authenticated(transport)
        try:
            self.read(client)
        except errors.D2MalformedResponse as error:
            frames = []
            current = error.__traceback__
            while current is not None:
                if current.tb_frame.f_globals.get("__name__") == session.__name__:
                    frames.append(current.tb_frame.f_code.co_name)
                    self.assertNotIn("token", current.tb_frame.f_locals)
                    self.assertNotIn("payload", current.tb_frame.f_locals)
                current = current.tb_next
            self.assertEqual(frames, ["read_json"])
            self.assertIsNone(error.__context__)
        else:
            self.fail("Expected private safe failure")

    def test_http_auth_failure_invalidates_even_when_cancellation_or_timeout_wins(self):
        for cancelled in (False, True):
            transport = Mock()
            client = self.authenticated(transport)
            stop = Event()
            def expired(*_args, **_options):
                if cancelled:
                    stop.set()
                else:
                    self.clock.value = 31
                return session._HttpResult(401, b"")
            transport.exchange.side_effect = expired
            self.clock.value = 10
            expected = errors.D2Cancelled if cancelled else errors.D2Timeout
            with self.assertRaises(expected):
                client.read_json(PATH, deadline=30, stop_event=stop, max_bytes=1024)
            self.assertFalse(client.is_authenticated())

    def test_envelope_auth_failure_invalidates_even_when_cancellation_wins(self):
        transport = Mock()
        transport.exchange.return_value = session._HttpResult(200, b'{"code":401}')
        client = self.authenticated(transport)
        stop = Event()
        def decode(_body):
            stop.set()
            return {"code": 401}
        with patch("sim_manager.devices.d2.session.json.loads", side_effect=decode):
            with self.assertRaises(errors.D2Cancelled):
                client.read_json(PATH, deadline=30, stop_event=stop, max_bytes=1024)
        self.assertFalse(client.is_authenticated())

    def test_unexpected_transport_exception_is_sanitized(self):
        transport = Mock()
        transport.exchange.side_effect = RuntimeError(PRIVATE_PASSWORD + PRIVATE_TOKEN)
        with self.assertRaises(errors.D2ConnectionError) as caught:
            self.read(self.authenticated(transport))
        output = "".join(traceback.format_exception(caught.exception))
        self.assertNotIn(PRIVATE_PASSWORD, output)
        self.assertNotIn(PRIVATE_TOKEN, output)
        self.assertIsNone(caught.exception.__context__)

    def test_cancelled_before_request_does_no_io(self):
        transport = Mock()
        client = self.authenticated(transport)
        stop = Event()
        stop.set()
        with self.assertRaises(errors.D2Cancelled):
            client.read_json(PATH, deadline=30, stop_event=stop, max_bytes=1024)
        transport.exchange.assert_not_called()

    def test_late_transport_result_discarded_on_invalidate(self):
        transport = Mock()
        client = self.authenticated(transport)
        def late(*_args, **_kwargs):
            client.invalidate()
            return session._HttpResult(200, b'{"code":200}')
        transport.exchange.side_effect = late
        with self.assertRaises(errors.D2Cancelled):
            self.read(client)
        self.assertFalse(client.is_authenticated())

    def test_close_cancels_active_session_and_is_idempotent(self):
        transport = Mock()
        client = self.authenticated(transport)
        active_stop = client._session_stop
        client.close()
        client.close()
        self.assertTrue(active_stop.is_set())
        self.assertFalse(client.is_authenticated())
        with self.assertRaises(errors.D2Cancelled):
            self.read(client)
        with self.assertRaises(errors.D2Cancelled):
            client.authenticate(PRIVATE_PASSWORD, username=PRIVATE_USERNAME)
        transport.exchange.assert_not_called()

    def test_close_interrupts_in_progress_socket_read(self):
        sock = FakeSocket([ssl.SSLWantReadError()])
        client = self.authenticated(self.transport(sock))
        def wait(*_args):
            client.close()
            return [], [], []
        with patch("select.select", side_effect=wait):
            with self.assertRaises(errors.D2Cancelled):
                self.read(client)
        self.assertTrue(sock.closed)
        self.assertFalse(client.is_authenticated())

    def test_payload_decoding_cannot_return_a_late_response(self):
        transport = Mock()
        transport.exchange.return_value = session._HttpResult(200, b'{"code":200}')
        client = self.authenticated(transport)
        def decode(_body):
            self.clock.value = 31
            return {"code": 200}
        with patch("sim_manager.devices.d2.session.json.loads", side_effect=decode):
            with self.assertRaises(errors.D2Timeout):
                self.read(client)

    def test_invalid_path_limit_deadline_validation(self):
        client = self.authenticated(Mock())
        for path, deadline, limit in [("/wrong", 30, 1024), (PATH, float("inf"), 1024),
                                      (PATH, True, 1024), (PATH, 30, 0), (PATH, 30, True),
                                      (PATH, 30, 256 * 1024 + 1)]:
            with self.assertRaises(ValueError):
                client.read_json(path, deadline=deadline, stop_event=None, max_bytes=limit)

    def test_invalid_password_timeout_and_cancel_are_private(self):
        client = session.D2Session(_transport=Mock())
        for timeout in [False, 0, -1, float("inf"), "secret"]:
            with self.assertRaises(ValueError):
                client.authenticate(PRIVATE_PASSWORD, username=PRIVATE_USERNAME, timeout=timeout)
        with self.assertRaises(ValueError):
            client.authenticate("", username=PRIVATE_USERNAME)
        for username in ("", " ", None):
            with self.assertRaises(ValueError):
                client.authenticate(PRIVATE_PASSWORD, username=username)
        stop = Event()
        stop.set()
        with self.assertRaises(errors.D2Cancelled):
            client.authenticate(PRIVATE_PASSWORD, username=PRIVATE_USERNAME, stop_event=stop)

    def test_all_error_classes_discard_sensitive_constructor_arguments(self):
        classes = [value for value in vars(errors).values()
                   if isinstance(value, type) and issubclass(value, errors.D2SessionError)]
        for cls in classes:
            with self.subTest(error=cls.__name__):
                error = cls(PRIVATE_PASSWORD, PRIVATE_TOKEN)
                self.assertNotIn(PRIVATE_PASSWORD, str(error))
                self.assertNotIn(PRIVATE_TOKEN, repr(error))
                self.assertNotIn(PRIVATE_TOKEN, repr(error.args))


if __name__ == "__main__":
    unittest.main()
