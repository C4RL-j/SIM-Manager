"""Private D2 HTTPS/session infrastructure, independent of browsers and Qt.

All network phases use nonblocking sockets and a shared monotonic deadline.
Only a configured private IP literal is accepted, avoiding blocking DNS work.
The optional public router certificate is an explicit trust anchor; certificate
verification is never disabled. Passwords and session material stay in memory.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
import ipaddress
from importlib import resources
import json
import math
import select
import socket
import ssl
import time
from collections.abc import Callable
from threading import Event, Lock
from urllib.parse import urlsplit

from .errors import (
    D2AuthenticationRejected, D2AuthenticationRequired, D2Cancelled,
    D2ConnectionError, D2MalformedAuthentication, D2MalformedResponse,
    D2MissingSessionToken, D2ResponseTooLarge, D2SessionError, D2Timeout,
    D2Unreachable,
)
from . import status as _status


_HEADER_LIMIT = 16 * 1024
_POLL = 0.05
_STATUS_PATHS = frozenset(_status.ENDPOINTS.values())
_LOGIN_PATH = "/web/v1/user/login"
_LOGIN_RESPONSE_LIMIT = 64 * 1024


def _is_header_token(value: object) -> bool:
    return (type(value) is str and 0 < len(value) <= 4096 and bool(value.strip())
            and all(32 <= ord(character) < 127 for character in value))


@dataclass(frozen=True, slots=True, repr=False)
class _HttpResult:
    status: int
    body: bytes

    def __repr__(self) -> str:
        return "_HttpResult(<details omitted>)"


def _origin_parts(origin: str) -> tuple[str, str, int, int]:
    try:
        parsed = urlsplit(origin)
        address = ipaddress.ip_address(parsed.hostname or "")
        if (parsed.scheme != "https" or not address.is_private
                or address.is_unspecified or address.is_multicast
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or "%" in str(address)):
            raise ValueError
        port = parsed.port if parsed.port is not None else 443
        if not 1 <= port <= 65535:
            raise ValueError
        host = str(address)
        host_header = f"[{host}]" if address.version == 6 else host
        authority = host_header if port == 443 else f"{host_header}:{port}"
        return f"https://{authority}", host, port, address.version
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Router address must be an HTTPS private IP origin.") from None


def _duration(timeout: float) -> float:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError("Router timeout must be a positive finite number.")
    try:
        duration = float(timeout)
    except (ValueError, OverflowError):
        raise ValueError("Router timeout must be a positive finite number.") from None
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Router timeout must be a positive finite number.")
    return duration


class _HttpsTransport:
    """One HTTPS connection per request; no cookies, redirects, or retries."""

    def __init__(
        self, origin: str, *, trusted_certificate: str | None = None,
        clock: Callable[[], float] = time.monotonic,
        socket_factory: Callable[..., socket.socket] | None = None,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self.origin, self._host, self._port, self._version = _origin_parts(origin)
        self._clock = clock
        self._socket_factory = socket_factory if socket_factory is not None else socket.socket
        if ssl_context is None:
            try:
                if trusted_certificate is None:
                    ssl_context = ssl.create_default_context()
                else:
                    # A dedicated anchor must not retain unrelated public CAs
                    # for this firmware certificate. Its verified SAN names
                    # the router IP, so hostname verification stays enabled.
                    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                    ssl_context.load_verify_locations(cadata=trusted_certificate)
            except (ValueError, ssl.SSLError, OSError):
                raise D2ConnectionError() from None
        if ssl_context.verify_mode != ssl.CERT_REQUIRED:
            raise ValueError("Router TLS certificate verification is required.")
        self._context = ssl_context

    def __repr__(self) -> str:
        return "_HttpsTransport(<details omitted>)"

    def _check(self, deadline: float, stop_event: Event | None, session_stop: Event) -> None:
        if session_stop.is_set() or (stop_event is not None and stop_event.is_set()):
            raise D2Cancelled() from None
        if self._clock() >= deadline:
            raise D2Timeout() from None

    def _wait(self, sock: socket.socket, *, reading: bool, deadline: float,
              stop_event: Event | None, session_stop: Event) -> None:
        while True:
            self._check(deadline, stop_event, session_stop)
            delay = min(_POLL, max(0.0, deadline - self._clock()))
            ready_read, ready_write, exceptional = select.select(
                [sock] if reading else [], [] if reading else [sock], [sock], delay,
            )
            self._check(deadline, stop_event, session_stop)
            if exceptional:
                raise D2ConnectionError() from None
            if ready_read or ready_write:
                return

    def exchange(
        self, method: str, path: str, *, body: bytes, authorization: str | None,
        deadline: float, stop_event: Event | None, session_stop: Event,
        max_bytes: int,
    ) -> _HttpResult:
        status_get = method == "GET" and path in _STATUS_PATHS and not body
        login_post = (method == "POST" and path == _LOGIN_PATH
                      and type(body) is bytes and 0 < len(body) <= 32 * 1024
                      and authorization is None)
        if not (status_get or login_post):
            raise ValueError("Router request is not permitted.") from None
        if authorization is not None and not _is_header_token(authorization):
            authorization = None
            raise D2ConnectionError() from None
        failure_type: type[D2SessionError] | None = None
        try:
            return self._perform_exchange(
                method, path, body=body, authorization=authorization,
                deadline=deadline, stop_event=stop_event,
                session_stop=session_stop, max_bytes=max_bytes,
            )
        except D2SessionError as caught:
            failure_type = type(caught)
        except Exception:
            failure_type = D2ConnectionError
        finally:
            authorization = None
            body = b""
        # A fresh exception outside the handler cannot retain an SSL/socket
        # exception or transport traceback containing private wire material.
        raise failure_type() from None

    def _perform_exchange(
        self, method: str, path: str, *, body: bytes, authorization: str | None,
        deadline: float, stop_event: Event | None, session_stop: Event,
        max_bytes: int,
    ) -> _HttpResult:
        sock = None
        connected = False
        try:
            self._check(deadline, stop_event, session_stop)
            sock = self._socket_factory(
                socket.AF_INET6 if self._version == 6 else socket.AF_INET,
                socket.SOCK_STREAM,
            )
            sock.setblocking(False)
            error = sock.connect_ex((self._host, self._port))
            pending = {0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY,
                       getattr(errno, "WSAEWOULDBLOCK", 10035),
                       getattr(errno, "WSAEINPROGRESS", 10036)}
            if error not in pending:
                raise D2Unreachable() from None
            if error:
                self._wait(sock, reading=False, deadline=deadline,
                           stop_event=stop_event, session_stop=session_stop)
                if sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR):
                    raise D2Unreachable() from None
            connected = True
            self._check(deadline, stop_event, session_stop)
            sock = self._context.wrap_socket(
                sock, server_hostname=self._host, do_handshake_on_connect=False,
            )
            while True:
                self._check(deadline, stop_event, session_stop)
                try:
                    sock.do_handshake()
                    break
                except ssl.SSLWantReadError:
                    self._wait(sock, reading=True, deadline=deadline,
                               stop_event=stop_event, session_stop=session_stop)
                except ssl.SSLWantWriteError:
                    self._wait(sock, reading=False, deadline=deadline,
                               stop_event=stop_event, session_stop=session_stop)

            host_header = self.origin[len("https://"):]
            headers = [f"{method} {path} HTTP/1.1", f"Host: {host_header}",
                       "Accept: application/json", "Connection: close"]
            if authorization is not None:
                headers.append(f"Authorization: {authorization}")
            if body:
                headers.extend(["Content-Type: application/json;charset=utf-8",
                                f"Content-Length: {len(body)}"])
            outgoing = ("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + body
            offset = 0
            while offset < len(outgoing):
                self._check(deadline, stop_event, session_stop)
                try:
                    count = sock.send(outgoing[offset:])
                    if count == 0:
                        raise D2ConnectionError() from None
                    offset += count
                except (ssl.SSLWantWriteError, BlockingIOError):
                    self._wait(sock, reading=False, deadline=deadline,
                               stop_event=stop_event, session_stop=session_stop)
                except ssl.SSLWantReadError:
                    self._wait(sock, reading=True, deadline=deadline,
                               stop_event=stop_event, session_stop=session_stop)

            def receive() -> bytes:
                while True:
                    self._check(deadline, stop_event, session_stop)
                    try:
                        chunk = sock.recv(8192)
                        self._check(deadline, stop_event, session_stop)
                        return chunk
                    except (ssl.SSLWantReadError, BlockingIOError):
                        self._wait(sock, reading=True, deadline=deadline,
                                   stop_event=stop_event, session_stop=session_stop)
                    except ssl.SSLWantWriteError:
                        self._wait(sock, reading=False, deadline=deadline,
                                   stop_event=stop_event, session_stop=session_stop)

            buffer = bytearray()
            while b"\r\n\r\n" not in buffer:
                chunk = receive()
                if not chunk:
                    raise D2ConnectionError() from None
                buffer.extend(chunk)
                if len(buffer.split(b"\r\n\r\n", 1)[0]) > _HEADER_LIMIT:
                    raise D2MalformedResponse() from None
            head, initial = bytes(buffer).split(b"\r\n\r\n", 1)
            lines = head.split(b"\r\n")
            try:
                version, status_text, *_reason = lines[0].split(b" ", 2)
                if version not in (b"HTTP/1.0", b"HTTP/1.1") or not status_text.isdigit():
                    raise ValueError
                status = int(status_text)
                if status < 200 or status > 599:
                    raise ValueError
                if status in (401, 403):
                    return _HttpResult(status, b"")
                headers_by_name: dict[bytes, bytes] = {}
                for line in lines[1:]:
                    name, value = line.split(b":", 1)
                    name = name.lower()
                    if not name or name in headers_by_name or name.strip() != name:
                        raise ValueError
                    headers_by_name[name] = value.strip()
            except (ValueError, OverflowError):
                raise D2MalformedResponse() from None
            if 300 <= status < 400:
                raise D2ConnectionError() from None

            content_length = headers_by_name.get(b"content-length")
            transfer = headers_by_name.get(b"transfer-encoding")
            if transfer is not None and (transfer.lower() != b"chunked" or content_length is not None):
                raise D2MalformedResponse() from None
            if headers_by_name.get(b"content-encoding", b"identity").lower() != b"identity":
                raise D2MalformedResponse() from None
            if transfer is not None:
                data = self._read_chunked(initial, receive, max_bytes)
            elif content_length is not None:
                if not content_length.isdigit():
                    raise D2MalformedResponse() from None
                length = int(content_length)
                if length > max_bytes:
                    raise D2ResponseTooLarge() from None
                data_buffer = bytearray(initial)
                while len(data_buffer) < length:
                    chunk = receive()
                    if not chunk:
                        raise D2ConnectionError() from None
                    data_buffer.extend(chunk)
                if len(data_buffer) != length:
                    raise D2MalformedResponse() from None
                data = bytes(data_buffer)
            else:
                data_buffer = bytearray(initial)
                while True:
                    if len(data_buffer) > max_bytes:
                        raise D2ResponseTooLarge() from None
                    chunk = receive()
                    if not chunk:
                        break
                    data_buffer.extend(chunk)
                data = bytes(data_buffer)
            self._check(deadline, stop_event, session_stop)
            return _HttpResult(status, data)
        except D2SessionError:
            raise
        except (ssl.SSLError, ValueError):
            raise D2ConnectionError() from None
        except OSError:
            if connected:
                raise D2ConnectionError() from None
            raise D2Unreachable() from None
        finally:
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass

    @staticmethod
    def _read_chunked(initial: bytes, receive: Callable[[], bytes], max_bytes: int) -> bytes:
        buffer = bytearray(initial)
        output = bytearray()
        overhead = 0

        def fill(size: int) -> None:
            while len(buffer) < size:
                chunk = receive()
                if not chunk:
                    raise D2ConnectionError() from None
                buffer.extend(chunk)

        while True:
            while b"\r\n" not in buffer:
                if len(buffer) > 128:
                    raise D2MalformedResponse() from None
                fill(len(buffer) + 1)
            line, remainder = bytes(buffer).split(b"\r\n", 1)
            buffer[:] = remainder
            overhead += len(line) + 2
            if overhead > _HEADER_LIMIT or len(line) > 128:
                raise D2MalformedResponse() from None
            size_text = line.split(b";", 1)[0]
            if not size_text or any(char not in b"0123456789abcdefABCDEF" for char in size_text):
                raise D2MalformedResponse() from None
            size = int(size_text, 16)
            if size == 0:
                # Trailer headers are unnecessary for JSON and cannot supply
                # authentication material. Reject them rather than retaining.
                fill(2)
                if buffer != b"\r\n":
                    raise D2MalformedResponse() from None
                return bytes(output)
            if size > max_bytes - len(output):
                raise D2ResponseTooLarge() from None
            fill(size + 2)
            if buffer[size:size + 2] != b"\r\n":
                raise D2MalformedResponse() from None
            output.extend(buffer[:size])
            del buffer[:size + 2]


class D2Session:
    """Own direct, user-initiated login and the bounded seven-getter transport.

    The firmware's editable username and password are sent verbatim as JSON;
    its returned Authorization value is forwarded without an added prefix.
    """

    def __init__(
        self, origin: str = "https://192.168.1.1", *,
        trusted_certificate: str | None = None,
        _clock: Callable[[], float] = time.monotonic,
        _transport: _HttpsTransport | None = None,
    ) -> None:
        self.origin, _, _, _ = _origin_parts(origin)
        self._clock = _clock
        if (_transport is None and trusted_certificate is None
                and self.origin == "https://192.168.1.1"):
            try:
                trusted_certificate = resources.files("sim_manager.resources").joinpath(
                    "d2-server.pem",
                ).read_text(encoding="ascii")
            except (OSError, ValueError):
                raise D2ConnectionError() from None
        self._transport = _transport if _transport is not None else _HttpsTransport(
            self.origin, trusted_certificate=trusted_certificate, clock=_clock,
        )
        self._lock = Lock()
        self._login_lock = Lock()
        self._generation = 0
        self._session_stop = Event()
        self._token: str | None = None
        self._closed = False

    def __repr__(self) -> str:
        return "D2Session(<details omitted>)"

    def is_authenticated(self) -> bool:
        with self._lock:
            return self._token is not None

    def invalidate(self) -> None:
        with self._lock:
            self._session_stop.set()
            self._generation += 1
            self._session_stop = Event()
            self._token = None
            if self._closed:
                self._session_stop.set()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._generation += 1
            self._token = None
            self._session_stop.set()

    def authenticate(
        self, password: str, *, username: str, timeout: float = 20.0,
        stop_event: Event | None = None,
    ) -> None:
        failure_type: type[Exception] | None = None
        acquired = False
        generation = None
        body = b""
        response = payload = data = token = None
        try:
            deadline = self._clock() + _duration(timeout)
            if not math.isfinite(deadline):
                raise ValueError("Router deadline must be finite.")
            with self._lock:
                if self._closed:
                    raise D2Cancelled() from None
            if stop_event is not None and stop_event.is_set():
                raise D2Cancelled() from None
            if not isinstance(password, str) or not password or len(password) > 4096:
                raise ValueError("Enter a router password.") from None
            if not isinstance(username, str) or not username.strip() or len(username) > 256:
                raise ValueError("Enter a router username.") from None
            acquired = self._login_lock.acquire(blocking=False)
            if not acquired:
                raise D2Cancelled() from None
            with self._lock:
                if self._closed:
                    raise D2Cancelled() from None
                self._session_stop.set()
                self._generation += 1
                self._token = None
                self._session_stop = Event()
                generation, session_stop = self._generation, self._session_stop
            body = json.dumps(
                {"username": username, "password": password},
                ensure_ascii=False, separators=(",", ":"),
            ).encode("utf-8")
            password = username = ""
            response = self._transport.exchange(
                "POST", _LOGIN_PATH, body=body, authorization=None,
                deadline=deadline, stop_event=stop_event,
                session_stop=session_stop, max_bytes=_LOGIN_RESPONSE_LIMIT,
            )
            if session_stop.is_set() or (stop_event is not None and stop_event.is_set()):
                raise D2Cancelled() from None
            if self._clock() >= deadline:
                raise D2Timeout() from None
            if response.status in (401, 403):
                raise D2AuthenticationRejected() from None
            if response.status != 200:
                raise D2ConnectionError() from None
            payload = json.loads(response.body.decode("utf-8"))
            if not isinstance(payload, dict) or type(payload.get("code")) is not int:
                raise D2MalformedAuthentication() from None
            if payload["code"] != 200:
                raise D2AuthenticationRejected() from None
            data = payload.get("data")
            if not isinstance(data, dict):
                raise D2MalformedAuthentication() from None
            token = data.get("Authorization")
            if not _is_header_token(token):
                raise D2MissingSessionToken() from None
            if session_stop.is_set() or (stop_event is not None and stop_event.is_set()):
                raise D2Cancelled() from None
            if self._clock() >= deadline:
                raise D2Timeout() from None
            with self._lock:
                if self._closed or generation != self._generation or session_stop.is_set():
                    raise D2Cancelled() from None
                self._token = token
        except D2SessionError as caught:
            failure_type = type(caught)
        except (UnicodeError, json.JSONDecodeError, RecursionError):
            failure_type = D2MalformedAuthentication
        except ValueError:
            failure_type = ValueError if generation is None else D2MalformedAuthentication
        except Exception:
            failure_type = D2MalformedAuthentication
        finally:
            password = username = ""
            body = b""
            response = payload = data = token = None
            if failure_type is not None and generation is not None:
                self._invalidate_generation(generation)
            if acquired:
                self._login_lock.release()
        if failure_type is ValueError:
            raise ValueError("Enter valid router credentials and timeout.") from None
        if failure_type is not None:
            raise failure_type() from None

    def _invalidate_generation(self, generation: int) -> None:
        with self._lock:
            if generation == self._generation:
                self._session_stop.set()
                self._generation += 1
                self._session_stop = Event()
                self._token = None

    def read_json(
        self, path: str, *, deadline: float, stop_event: Event | None,
        max_bytes: int,
    ) -> _status.StatusResponse:
        failure_type: type[Exception] | None = None
        try:
            return self._read_json(
                path, deadline=deadline, stop_event=stop_event, max_bytes=max_bytes,
            )
        except D2SessionError as caught:
            failure_type = type(caught)
        except ValueError:
            failure_type = ValueError
        except Exception:
            failure_type = D2MalformedResponse
        if failure_type is ValueError:
            raise ValueError("Invalid router status request.") from None
        # Discard internal traceback frames that may hold the token or raw
        # payload even when the underlying error message is already safe.
        raise failure_type() from None

    def _read_json(
        self, path: str, *, deadline: float, stop_event: Event | None,
        max_bytes: int,
    ) -> _status.StatusResponse:
        if not isinstance(path, str) or path not in _STATUS_PATHS:
            raise ValueError("Router status path is not permitted.") from None
        if (isinstance(deadline, bool) or not isinstance(deadline, (int, float))
                or not math.isfinite(deadline)):
            raise ValueError("Router deadline must be finite.") from None
        if type(max_bytes) is not int or not 1 <= max_bytes <= 256 * 1024:
            raise ValueError("Router response limit is invalid.") from None
        if stop_event is not None and stop_event.is_set():
            raise D2Cancelled() from None
        if self._clock() >= deadline:
            raise D2Timeout() from None
        with self._lock:
            token, generation, session_stop = self._token, self._generation, self._session_stop
            if self._closed:
                raise D2Cancelled() from None
        if token is None:
            raise D2AuthenticationRequired() from None
        transport_failed = False
        try:
            response = self._transport.exchange(
                "GET", path, body=b"", authorization=token, deadline=deadline,
                stop_event=stop_event, session_stop=session_stop, max_bytes=max_bytes,
            )
        except D2SessionError:
            raise
        except Exception:
            transport_failed = True
        if transport_failed:
            raise D2ConnectionError() from None
        was_invalidated = session_stop.is_set()
        expired = response.status in (401, 403)
        if expired:
            self._invalidate_generation(generation)
        if was_invalidated or (stop_event is not None and stop_event.is_set()):
            raise D2Cancelled() from None
        if self._clock() >= deadline:
            raise D2Timeout() from None
        if expired:
            raise D2AuthenticationRequired() from None
        malformed = False
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (ValueError, UnicodeError, RecursionError):
            malformed = True
        if malformed:
            # Raising outside the decoder's except block avoids retaining its
            # JSONDecodeError.doc (the raw private response) as __context__.
            raise D2MalformedResponse() from None
        code = payload.get("code") if isinstance(payload, dict) else None
        was_invalidated = session_stop.is_set()
        expired = type(code) is int and code in (401, 403)
        if expired:
            self._invalidate_generation(generation)
        if was_invalidated or (stop_event is not None and stop_event.is_set()):
            raise D2Cancelled() from None
        if self._clock() >= deadline:
            raise D2Timeout() from None
        if expired:
            raise D2AuthenticationRequired() from None
        return _status.StatusResponse(response.status, payload)
