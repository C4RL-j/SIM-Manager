"""D2 Telnet/UBus SMS transport; no carrier interpretation or diagnostic payloads."""

from __future__ import annotations

import json
import math
import socket
import threading
import time
from typing import Any, Callable, Dict, List

ROUTER_HOST = "192.168.1.1"
ROUTER_PORT = 2323
READ_NUM = 3
MAX_RESPONSE_BYTES = 1024 * 1024
SOCKET_POLL_SECONDS = 0.5
CANCELLABLE_POLL_SECONDS = 0.1
CONNECT_POLL_SECONDS = 0.05

IAC = 255
DONT = 254
DO = 253
WONT = 252
WILL = 251
SB = 250
SE = 240


class RouterError(Exception):
    """Base class for sanitized router errors."""


class RouterConnectionError(RouterError):
    """The router cannot be reached or an I/O operation failed."""


class RouterDisconnectedError(RouterConnectionError):
    """The connected router closed or reset the connection."""


class RouterTimeoutError(RouterError):
    """A router operation exceeded its deadline."""


class RouterLoginRequiredError(RouterError):
    """The router Telnet service requests credentials."""


class RouterResponseError(RouterError):
    """The response is incomplete, unrecognizable, or too large."""


class RouterCancelledError(RouterError):
    """The caller requested cooperative cancellation."""


def _check_cancelled(stop_event: threading.Event | None) -> None:
    if stop_event is not None and stop_event.is_set():
        raise RouterCancelledError("Router operation cancelled.") from None


def _deadline(timeout: float) -> float:
    if not math.isfinite(timeout) or timeout < 0:
        raise ValueError("Timeout must be finite and non-negative.")
    return time.monotonic() + timeout


def _check_size_limit(max_response_bytes: int) -> None:
    if (
        not isinstance(max_response_bytes, int)
        or isinstance(max_response_bytes, bool)
        or max_response_bytes <= 0
    ):
        raise ValueError("Response size limit must be a positive integer.")


def _close_socket(sock: socket.socket | None) -> None:
    if sock is not None:
        try:
            sock.close()
        except OSError:
            pass  # Cleanup must not hide cancellation or reveal OS details.


def _connection_failure(error: BaseException) -> None:
    if isinstance(error, ConnectionRefusedError):
        raise RouterConnectionError(
            "Connection refused. The D2 Telnet service on port 2323 may not be running."
        ) from None
    if isinstance(error, (socket.timeout, TimeoutError)):
        raise RouterTimeoutError("Timed out connecting to the router.") from None
    raise RouterConnectionError("Could not connect to the router.") from None


def _connect(
    host: str, port: int, connect_timeout: float, stop_event: threading.Event | None
) -> socket.socket:
    """Bound caller waits even if platform DNS/connect remains blocked.

    An abandoned daemon worker owns and closes any socket that arrives later.
    The lock covers cancellation/completion races; no join blocks shutdown.
    OS resolution itself is not forcibly interrupted.
    """
    deadline = _deadline(connect_timeout)
    _check_cancelled(stop_event)
    done = threading.Event()
    lock = threading.Lock()
    result: dict[str, Any] = {}
    abandoned = False

    def connect_worker() -> None:
        try:
            connected = socket.create_connection((host, port), timeout=connect_timeout)
        except BaseException as error:
            # Never let a worker traceback print endpoint/OS details.
            with lock:
                if not abandoned:
                    result["error"] = error
        else:
            with lock:
                if abandoned:
                    _close_socket(connected)
                else:
                    result["socket"] = connected
        finally:
            done.set()

    try:
        if connect_timeout == 0:
            raise RouterTimeoutError("Timed out connecting to the router.")
        worker = threading.Thread(target=connect_worker, name="D2Connect", daemon=True)
        try:
            worker.start()
        except RuntimeError:
            raise RouterConnectionError("Could not start the router connection.") from None
        while True:
            _check_cancelled(stop_event)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RouterTimeoutError("Timed out connecting to the router.")
            if done.wait(min(CONNECT_POLL_SECONDS, remaining)):
                break
        _check_cancelled(stop_event)
        if time.monotonic() >= deadline:
            raise RouterTimeoutError("Timed out connecting to the router.")
        with lock:
            error = result.get("error")
            connected = result.pop("socket", None)
        if error is not None:
            _connection_failure(error)
        if connected is None:
            raise RouterConnectionError("Could not connect to the router.")
        return connected
    finally:
        with lock:
            abandoned = True
            leftover = result.pop("socket", None)
        _close_socket(leftover)


class TelnetDecoder:
    """Keep negotiation state across TCP chunks and shell read phases."""

    def __init__(self) -> None:
        self.state = "data"
        self.command = 0

    def feed(
        self,
        sock: socket.socket,
        data: bytes,
        *,
        before_reply: Callable[[], None] | None = None,
    ) -> bytes:
        out = bytearray()
        for value in data:
            if self.state == "data":
                if value == IAC:
                    self.state = "iac"
                else:
                    out.append(value)
            elif self.state == "iac":
                if value == IAC:
                    out.append(IAC)
                    self.state = "data"
                elif value in (WILL, WONT, DO, DONT):
                    self.command = value
                    self.state = "option"
                elif value == SB:
                    self.state = "subnegotiation"
                else:
                    self.state = "data"
            elif self.state == "option":
                if self.command in (WILL, DO) and before_reply is not None:
                    before_reply()
                try:
                    if self.command == WILL:
                        sock.sendall(bytes([IAC, DONT, value]))
                    elif self.command == DO:
                        sock.sendall(bytes([IAC, WONT, value]))
                except OSError:
                    pass  # Preserve best-effort refusal of unsupported options.
                self.state = "data"
            elif self.state == "subnegotiation":
                if value == IAC:
                    self.state = "subnegotiation_iac"
            elif self.state == "subnegotiation_iac":
                self.state = "data" if value == SE else "subnegotiation"
        return bytes(out)


def handle_telnet_bytes(
    sock: socket.socket, data: bytes, *, decoder: TelnetDecoder | None = None
) -> bytes:
    return (decoder if decoder is not None else TelnetDecoder()).feed(sock, data)


class _CompletionMarker:
    """Match a terminated whole line, never an echoed command or JSON text."""

    def __init__(self, marker: str) -> None:
        self.marker = marker.encode("ascii")
        self.position = 0
        self.possible = True

    def feed(self, data: bytes) -> int | None:
        for offset, value in enumerate(data, 1):
            if value in (10, 13):
                if self.possible and self.position == len(self.marker):
                    return offset
                self.position = 0
                self.possible = True
            elif self.possible:
                if self.position < len(self.marker) and value == self.marker[self.position]:
                    self.position += 1
                else:
                    self.possible = False
        return None


def _receive(
    sock: socket.socket,
    deadline: float,
    decoder: TelnetDecoder,
    stop_event: threading.Event | None,
    max_response_bytes: int,
    marker: str | None = None,
) -> str:
    chunks = []
    raw_size = 0
    completion = _CompletionMarker(marker) if marker is not None else None
    poll = CANCELLABLE_POLL_SECONDS if stop_event is not None else SOCKET_POLL_SECONDS
    idle_deadline = None

    def before_reply() -> None:
        _check_cancelled(stop_event)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RouterTimeoutError("Timed out processing the router response.")
        # A single chunk can contain many negotiation writes. Bound each one,
        # rather than giving every reply a fresh full socket timeout.
        sock.settimeout(min(poll, remaining))

    while True:
        _check_cancelled(stop_event)
        now = time.monotonic()
        remaining = deadline - now
        if completion is None:
            if idle_deadline is None:
                idle_deadline = now + SOCKET_POLL_SECONDS
            remaining = min(remaining, idle_deadline - now)
        if remaining <= 0:
            break
        sock.settimeout(min(poll, remaining))
        try:
            data = sock.recv(16384)
        except socket.timeout:
            _check_cancelled(stop_event)
            # Short cancellation polls must not shorten the legacy idle wait.
            # The next iteration checks both idle and phase deadlines.
            continue
        _check_cancelled(stop_event)
        if not data:
            raise RouterDisconnectedError("The router disconnected before the response completed.")
        if completion is None:
            idle_deadline = time.monotonic() + SOCKET_POLL_SECONDS
        raw_size += len(data)
        if raw_size > max_response_bytes:
            raise RouterResponseError("Router response exceeded the configured size limit.")
        # Stop decoding at the printed line, even when another command's shell
        # output or Telnet negotiations share this TCP read.
        parts = []
        wire_parts = data.splitlines(keepends=True) if completion is not None else [data]
        for wire_part in wire_parts:
            clean = decoder.feed(sock, wire_part, before_reply=before_reply)
            _check_cancelled(stop_event)
            if not clean:
                continue
            end = completion.feed(clean) if completion is not None else None
            if end is not None:
                parts.append(clean[:end])
                chunks.append(b"".join(parts))
                return b"".join(chunks).decode("utf-8", errors="replace")
            parts.append(clean)
        if parts:
            chunks.append(b"".join(parts))
    _check_cancelled(stop_event)
    if completion is not None:
        raise RouterTimeoutError("Timed out waiting for the router SMS command to finish.")
    return b"".join(chunks).decode("utf-8", errors="replace")


def receive_some(
    sock: socket.socket,
    duration: float = 0.7,
    *,
    decoder: TelnetDecoder | None = None,
    stop_event: threading.Event | None = None,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
) -> str:
    _check_size_limit(max_response_bytes)
    return _receive(
        sock, _deadline(duration), decoder or TelnetDecoder(), stop_event, max_response_bytes
    )


def receive_until_marker_printed(
    sock: socket.socket,
    marker: str,
    timeout: float = 30.0,
    *,
    decoder: TelnetDecoder | None = None,
    stop_event: threading.Event | None = None,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
    deadline: float | None = None,
) -> str:
    """Wait for the printed marker line, with or without command echo."""
    _check_size_limit(max_response_bytes)
    return _receive(
        sock,
        _deadline(timeout) if deadline is None else deadline,
        decoder or TelnetDecoder(),
        stop_event,
        max_response_bytes,
        marker,
    )


def build_sms_command(read_num: int, marker: str) -> str:
    # Preserve the observed command, quoting, marker, and CRLF byte-for-byte.
    return (
        "ubus -t 10 call cped cmd "
        '\'{"cmd":"sms.get.inboxdata","arg":"{\\"StartPos\\":0,\\"ReadNum\\":'
        + str(read_num)
        + '}"}\''
        f"; echo {marker}\r\n"
    )


def extract_valid_json_objects(text: str) -> List[Dict[str, Any]]:
    """Retain the legacy helper's nested-object enumeration for compatibility."""
    results = []
    for start, ch in enumerate(text):
        if ch != "{":
            continue
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            c = text[i]
            if in_string:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == '"':
                    in_string = False
                continue
            if c == '"':
                in_string = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                    except (ValueError, RecursionError):
                        pass
                    else:
                        if isinstance(obj, dict):
                            results.append(obj)
                    break
    return results


def _is_success(obj: dict[str, Any]) -> bool:
    return obj.get("code") == 200 and obj.get("msg") == "ok" and "data" in obj


def _object_end(text: str, start: int, check_progress: Callable[[], None]) -> int | None:
    """Find the outer object's extent even when its JSON contents are invalid.

    Skipping a whole malformed object prevents nested SMS content from being
    promoted to a response. Balanced shell noise can still be skipped safely.
    """
    depth = 0
    in_string = False
    escaped = False
    for position in range(start, len(text)):
        if (position - start) % 1024 == 0:
            check_progress()
        value = text[position]
        if in_string:
            if escaped:
                escaped = False
            elif value == "\\":
                escaped = True
            elif value == '"':
                in_string = False
        elif value == '"':
            in_string = True
        elif value == "{":
            depth += 1
        elif value == "}":
            depth -= 1
            if depth == 0:
                return position + 1
    return None


def get_sms_response(
    shell_output: str,
    *,
    stop_event: threading.Event | None = None,
    deadline: float | None = None,
) -> Dict[str, Any]:
    """Prefer outer envelopes while preserving transparent legacy wrappers/data."""
    decoder = json.JSONDecoder()
    last_success = None
    wrapped_success = None
    saw_envelope = False
    position = 0

    def check_progress() -> None:
        _check_cancelled(stop_event)
        if deadline is not None and time.monotonic() >= deadline:
            raise RouterTimeoutError("Timed out parsing the router response.")

    while position < len(shell_output):
        check_progress()
        start = shell_output.find("{", position)
        if start < 0:
            break
        end = _object_end(shell_output, start, check_progress)
        if end is None:
            break
        position = end
        try:
            obj, decoded_end = decoder.raw_decode(shell_output, start)
        except (ValueError, RecursionError):
            continue
        if decoded_end != end:
            continue
        check_progress()
        if "code" in obj and "msg" in obj:
            saw_envelope = True
            if _is_success(obj):
                last_success = obj
            continue
        # Preserve transparent legacy wrappers only without an outer envelope.
        pending = list(reversed(list(obj.values())))
        while pending:
            check_progress()
            value = pending.pop()
            if isinstance(value, dict):
                if "code" in value and "msg" in value:
                    if _is_success(value):
                        wrapped_success = value
                    # A response's own payload is never another candidate,
                    # including when that response reports an error.
                else:
                    pending.extend(reversed(list(value.values())))
            elif isinstance(value, list):
                pending.extend(reversed(value))
    check_progress()
    if last_success is not None:
        return last_success
    if not saw_envelope and wrapped_success is not None:
        return wrapped_success
    raise RouterResponseError("Could not find a complete router SMS response.")


def _send(sock: socket.socket, data: bytes, stop_event: threading.Event | None) -> None:
    _check_cancelled(stop_event)
    sock.settimeout(
        CANCELLABLE_POLL_SECONDS if stop_event is not None else SOCKET_POLL_SECONDS
    )
    try:
        sock.sendall(data)
    except socket.timeout:
        _check_cancelled(stop_event)
        # A retry could duplicate a partially written shell command.
        raise RouterTimeoutError("Timed out sending a router command.") from None
    _check_cancelled(stop_event)


def fetch_sms_response(
    host: str = ROUTER_HOST,
    port: int = ROUTER_PORT,
    read_num: int = READ_NUM,
    connect_timeout: float = 3.0,
    response_timeout: float = 30.0,
    *,
    stop_event: threading.Event | None = None,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
) -> Dict[str, Any]:
    """Read the inbox with bounded waits and cooperative background cancellation.

    Set stop_event on shutdown. Data is returned as the legacy envelope; this
    transport never logs or interprets message content.
    """
    _check_size_limit(max_response_bytes)
    _deadline(response_timeout)  # Validate before any socket or worker exists.
    _check_cancelled(stop_event)
    marker = "__DITO_HELPER_END_91F7__"  # Historical token, no carrier logic.
    command = build_sms_command(read_num, marker)
    decoder = TelnetDecoder()
    options = {
        "decoder": decoder,
        "stop_event": stop_event,
        "max_response_bytes": max_response_bytes,
    }
    try:
        with _connect(host, port, connect_timeout, stop_event) as sock:
            _check_cancelled(stop_event)
            sock.settimeout(SOCKET_POLL_SECONDS)
            banner = receive_some(sock, 0.7, **options)
            if "login:" in banner.lower() or "password:" in banner.lower():
                raise RouterLoginRequiredError(
                    "The router is asking for a Telnet login. "
                    "A direct shell on port 2323 is required."
                )
            _send(sock, b"\r\n", stop_event)
            receive_some(sock, 0.25, **options)
            _send(sock, command.encode("utf-8"), stop_event)
            deadline = _deadline(response_timeout)
            output = receive_until_marker_printed(
                sock, marker, timeout=response_timeout, deadline=deadline, **options
            )
            return get_sms_response(output, stop_event=stop_event, deadline=deadline)
    except RouterError:
        raise
    except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
        _check_cancelled(stop_event)
        raise RouterDisconnectedError("The router connection was interrupted.") from None
    except (socket.timeout, TimeoutError):
        _check_cancelled(stop_event)
        raise RouterTimeoutError("A router operation timed out.") from None
    except OSError:
        _check_cancelled(stop_event)
        raise RouterConnectionError("Router communication failed.") from None
