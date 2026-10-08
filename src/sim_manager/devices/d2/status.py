"""Read-only aggregation of the seven verified D2 dashboard getters.

Authentication is delegated to a direct D2 session. A missing session remains
inert; the live service composes the production session independently.
Raw payloads live only at this device boundary and are never diagnostic output.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event
from types import MappingProxyType
from typing import Protocol

from sim_manager.models import DeviceIssue, DeviceState, IssueCode

from .errors import D2Cancelled, D2ConnectionError, D2Unreachable
from .status_parser import SOURCE_KEYS, normalize_status


ENDPOINTS = MappingProxyType({
    "wireless": "/web/v1/dashboard/wirelessinfo",
    "internet": "/web/v1/dashboard/internetinfo",
    "wan": "/web/v1/dashboard/waninfo",
    "device": "/web/v1/dashboard/deviceinfo",
    "wanStatus": "/web/v1/status/wanstatus",
    "sim": "/web/v1/setting/network/pinmanagement/simcardinfo",
    "deviceDetails": "/web/v1/setting/deviceinfo",
})
_MAX_RESPONSE_BYTES = 256 * 1024


@dataclass(frozen=True, slots=True, repr=False)
class StatusResponse:
    """Private device-boundary response, never returned to services or UI."""

    http_status: int
    payload: object

    def __repr__(self) -> str:
        return "StatusResponse(<details omitted>)"


class AuthenticatedStatusSession(Protocol):
    """Contract for a legitimate authenticated D2 HTTP session.

    Implementations must issue GET only to the supplied fixed path on their
    configured router origin, reject redirects, keep credentials private, and
    enforce their documented router-scoped TLS policy. They must bound the body by max_bytes and cooperate
    with the absolute monotonic deadline and stop_event during network reads.
    Cleanup belongs to the session that owns its connections. Exceptions must
    omit raw responses and authentication material.

    The client starts no workers and cannot preempt arbitrary injected Python
    code. A session that ignores these limits can still block its caller.
    """

    def read_json(
        self,
        path: str,
        *,
        deadline: float,
        stop_event: Event | None,
        max_bytes: int,
    ) -> StatusResponse:
        """Return the HTTP status and decoded JSON for one read-only GET."""
        ...


class D2StatusClient:
    """Return one normalized snapshot without exposing endpoint payloads."""

    def __init__(
        self,
        session: AuthenticatedStatusSession | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._session = session
        self._clock = clock
        self._now = now

    def __repr__(self) -> str:
        return "D2StatusClient(<details omitted>)"

    def get_device_state(
        self,
        *,
        timeout: float = 20.0,
        stop_event: Event | None = None,
    ) -> DeviceState:
        """Read the allowlist once, retaining successful partial telemetry.

        One deadline covers the entire snapshot. Cancellation and an expired
        deadline discard a late response; earlier successful reads survive.
        Authentication failure stops further requests. Other endpoint failures
        are represented by closed codes and do not invalidate earlier data.
        """
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError("Status timeout must be a positive finite number.")
        try:
            duration = float(timeout)
        except (OverflowError, ValueError):
            raise ValueError("Status timeout must be a positive finite number.") from None
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Status timeout must be a positive finite number.")

        deadline = self._clock() + duration
        if not math.isfinite(deadline):
            raise ValueError("Status deadline must be finite.")
        responses: dict[str, object] = {}
        errors: list[DeviceIssue] = []

        def mark_remaining(start: int, code: IssueCode) -> None:
            errors.extend(DeviceIssue(source, code) for source in SOURCE_KEYS[start:])

        def interruption() -> IssueCode | None:
            if stop_event is not None and stop_event.is_set():
                return IssueCode.CANCELLED
            if self._clock() >= deadline:
                return IssueCode.TIMEOUT
            return None

        for index, source in enumerate(SOURCE_KEYS):
            interrupted = interruption()
            if interrupted is not None:
                mark_remaining(index, interrupted)
                break
            if self._session is None:
                mark_remaining(index, IssueCode.AUTHENTICATION_REQUIRED)
                break

            failure: IssueCode | None = None
            response: StatusResponse | None = None
            try:
                response = self._session.read_json(
                    ENDPOINTS[source],
                    deadline=deadline,
                    stop_event=stop_event,
                    max_bytes=_MAX_RESPONSE_BYTES,
                )
            except PermissionError:
                failure = IssueCode.AUTHENTICATION_REQUIRED
            except D2Cancelled:
                failure = IssueCode.CANCELLED
            except TimeoutError:
                failure = IssueCode.TIMEOUT
            except D2Unreachable:
                failure = IssueCode.UNREACHABLE
            except D2ConnectionError:
                failure = IssueCode.CONNECTION_ERROR
            except ValueError:
                failure = IssueCode.MALFORMED_RESPONSE
            except Exception:
                failure = IssueCode.UNAVAILABLE

            # Expiry still invalidates authorization if cancellation/deadline
            # wins presentation priority at the same moment as the response.
            if failure is IssueCode.AUTHENTICATION_REQUIRED:
                self._invalidate_session()
            elif isinstance(response, StatusResponse):
                payload_code = response.payload.get("code") if isinstance(response.payload, dict) else None
                if response.http_status in (401, 403) or (type(payload_code) is int and payload_code in (401, 403)):
                    self._invalidate_session()

            interrupted = interruption()
            if interrupted is not None:
                mark_remaining(index, interrupted)
                break
            if failure is IssueCode.AUTHENTICATION_REQUIRED:
                mark_remaining(index, failure)
                break
            if failure is IssueCode.CANCELLED:
                mark_remaining(index, failure)
                break
            if failure is not None:
                errors.append(DeviceIssue(source, failure))
                continue
            if not isinstance(response, StatusResponse) or type(response.http_status) is not int:
                errors.append(DeviceIssue(source, IssueCode.MALFORMED_RESPONSE))
                continue

            payload = response.payload
            code = payload.get("code") if isinstance(payload, dict) else None
            if response.http_status in (401, 403) or (type(code) is int and code in (401, 403)):
                mark_remaining(index, IssueCode.AUTHENTICATION_REQUIRED)
                break
            if response.http_status != 200:
                errors.append(DeviceIssue(source, IssueCode.UNAVAILABLE))
                continue
            # Envelope and field validation belong to the pure normalizer.
            responses[source] = payload

        return normalize_status(responses, errors=tuple(errors), observed_at=self._now())

    def _invalidate_session(self) -> None:
        """Forget expired authorization without leaking implementation errors."""
        invalidate = getattr(self._session, "invalidate", None)
        if callable(invalidate):
            try:
                invalidate()
            except Exception:
                pass
