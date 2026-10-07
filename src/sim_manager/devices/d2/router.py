#!/usr/bin/env python3
"""
Router communication for DITO Desktop.

This module intentionally mirrors the working Telnet/UBus behavior from
dito_otp_helper.py so the GUI can reuse the proven router path.
"""

import json
import socket
import time
from typing import Any, Dict, List

ROUTER_HOST = "192.168.1.1"
ROUTER_PORT = 2323
READ_NUM = 3

IAC = 255
DONT = 254
DO = 253
WONT = 252
WILL = 251


class RouterError(Exception):
    """Base class for user-facing router errors."""


class RouterConnectionError(RouterError):
    """Raised when the router cannot be reached."""


class RouterTimeoutError(RouterError):
    """Raised when the router does not respond in time."""


class RouterLoginRequiredError(RouterError):
    """Raised when the router Telnet service asks for credentials."""


class RouterResponseError(RouterError):
    """Raised when the router responds but the SMS payload is incomplete."""


def handle_telnet_bytes(sock: socket.socket, data: bytes) -> bytes:
    out = bytearray()
    i = 0

    while i < len(data):
        if data[i] != IAC:
            out.append(data[i])
            i += 1
            continue

        if i + 1 >= len(data):
            break

        cmd = data[i + 1]

        if cmd == IAC:
            out.append(IAC)
            i += 2
            continue

        if cmd in (WILL, WONT, DO, DONT):
            if i + 2 >= len(data):
                break

            opt = data[i + 2]

            try:
                if cmd == WILL:
                    sock.sendall(bytes([IAC, DONT, opt]))
                elif cmd == DO:
                    sock.sendall(bytes([IAC, WONT, opt]))
            except OSError:
                pass

            i += 3
            continue

        i += 2

    return bytes(out)


def receive_some(sock: socket.socket, duration: float = 0.7) -> str:
    end = time.time() + duration
    chunks = []

    while time.time() < end:
        try:
            data = sock.recv(16384)
            if not data:
                break

            clean = handle_telnet_bytes(sock, data)
            if clean:
                chunks.append(clean)

        except socket.timeout:
            break

    return b"".join(chunks).decode("utf-8", errors="replace")


def receive_until_marker_printed(
    sock: socket.socket,
    marker: str,
    timeout: float = 30.0,
) -> str:
    """
    The router shell echoes the command we send. That echoed command already
    contains the marker once. Wait for the second marker from `echo MARKER`.
    """
    end = time.time() + timeout
    chunks = []

    while time.time() < end:
        try:
            data = sock.recv(16384)
            if not data:
                break

            clean = handle_telnet_bytes(sock, data)
            if clean:
                chunks.append(clean)

            text = b"".join(chunks).decode("utf-8", errors="replace")

            if text.count(marker) >= 2:
                return text

        except socket.timeout:
            continue

    return b"".join(chunks).decode("utf-8", errors="replace")


def build_sms_command(read_num: int, marker: str) -> str:
    return (
        "ubus -t 10 call cped cmd "
        '\'{"cmd":"sms.get.inboxdata","arg":"{\\"StartPos\\":0,\\"ReadNum\\":'
        + str(read_num)
        + '}"}\''
        f"; echo {marker}\r\n"
    )


def extract_valid_json_objects(text: str) -> List[Dict[str, Any]]:
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
                    candidate = text[start:i + 1]

                    try:
                        obj = json.loads(candidate)
                    except json.JSONDecodeError:
                        pass
                    else:
                        if isinstance(obj, dict):
                            results.append(obj)

                    break

    return results


def get_sms_response(shell_output: str) -> Dict[str, Any]:
    candidates = extract_valid_json_objects(shell_output)

    for obj in reversed(candidates):
        if (
            obj.get("code") == 200
            and obj.get("msg") == "ok"
            and "data" in obj
        ):
            return obj

    raise RouterResponseError("Could not find a complete router SMS response.")


def fetch_sms_response(
    host: str = ROUTER_HOST,
    port: int = ROUTER_PORT,
    read_num: int = READ_NUM,
    connect_timeout: float = 3.0,
    response_timeout: float = 30.0,
) -> Dict[str, Any]:
    marker = "__DITO_HELPER_END_91F7__"
    router_command = build_sms_command(read_num, marker)

    try:
        with socket.create_connection((host, port), timeout=connect_timeout) as sock:
            sock.settimeout(0.5)

            banner = receive_some(sock, 0.7)

            if "login:" in banner.lower() or "password:" in banner.lower():
                raise RouterLoginRequiredError(
                    "The router is asking for a Telnet login. DITO Desktop "
                    "expects the direct shell on port 2323."
                )

            sock.sendall(b"\r\n")
            receive_some(sock, 0.25)

            sock.sendall(router_command.encode("utf-8"))
            output = receive_until_marker_printed(
                sock,
                marker,
                timeout=response_timeout,
            )

    except ConnectionRefusedError as exc:
        raise RouterConnectionError(
            "Connection refused. The D2 Telnet service on port 2323 may not be running."
        ) from exc

    except (socket.timeout, TimeoutError) as exc:
        raise RouterTimeoutError("Timed out connecting to the router.") from exc

    except OSError as exc:
        raise RouterConnectionError(f"Could not connect to the router: {exc}") from exc

    if output.count(marker) < 2:
        raise RouterTimeoutError("Timed out waiting for the router SMS command to finish.")

    return get_sms_response(output)
