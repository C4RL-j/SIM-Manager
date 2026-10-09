"""Read-only snapshot providers; demo data is always an explicit choice."""

from __future__ import annotations

from enum import Enum
from threading import Event
from typing import Protocol

from sim_manager.devices.d2.demo import load_demo_state
from sim_manager.devices.d2.status import D2StatusClient
from sim_manager.devices.d2.errors import (
    D2AuthenticationRejected, D2Cancelled, D2ConnectionError,
    D2MalformedAuthentication, D2Timeout, D2Unreachable,
)
from sim_manager.devices.d2.session import D2Session
from sim_manager.models import DeviceState


class SnapshotProvider(Protocol):
    """The desktop refresh worker's normalized, credential-free interface."""

    is_demo: bool

    def get_device_state(self, *, stop_event: Event | None = None) -> DeviceState:
        ...


class RefreshCancelled(Exception):
    def __init__(self) -> None:
        super().__init__("Refresh cancelled.")


class AuthenticationFailure(str, Enum):
    REJECTED = "rejected"
    MALFORMED = "malformed"
    TIMEOUT = "timeout"
    UNREACHABLE = "unreachable"
    CONNECTION = "connection"
    CANCELLED = "cancelled"


_AUTH_MESSAGES = {
    AuthenticationFailure.REJECTED: "Authentication rejected",
    AuthenticationFailure.MALFORMED: "Malformed authentication response",
    AuthenticationFailure.TIMEOUT: "Router timed out",
    AuthenticationFailure.UNREACHABLE: "Router unreachable",
    AuthenticationFailure.CONNECTION: "Router connection problem",
    AuthenticationFailure.CANCELLED: "Sign-in cancelled",
}


class AuthenticationError(Exception):
    """Only closed, safe service outcomes may cross into desktop code."""

    def __init__(self, code: AuthenticationFailure) -> None:
        self.code = code if type(code) is AuthenticationFailure else AuthenticationFailure.MALFORMED
        super().__init__(_AUTH_MESSAGES[self.code])


def _check_cancelled(stop_event: Event | None) -> None:
    if stop_event is not None and stop_event.is_set():
        raise RefreshCancelled() from None


class LiveDeviceService:
    """Own the direct router session and expose normalized snapshots only."""

    is_demo = False

    def __init__(self, client: D2StatusClient | None = None, *, session: D2Session | None = None) -> None:
        self._session = session if session is not None else (D2Session() if client is None else None)
        self._client = client if client is not None else D2StatusClient(self._session)

    def __repr__(self) -> str:
        return "LiveDeviceService(<details omitted>)"

    @property
    def router_address(self) -> str:
        return self._session.origin if self._session is not None else "https://192.168.1.1"

    def authenticate(self, password: str, *, username: str, stop_event: Event | None = None) -> DeviceState:
        """One explicit login attempt, followed automatically by live refresh.

        Neither credentials nor authorization are stored by this service. The
        caller runs this operation on the same worker as ordinary refreshes.
        """
        failure: AuthenticationFailure | None = None
        try:
            if stop_event is not None and stop_event.is_set():
                raise D2Cancelled()
            if (not isinstance(password, str) or not password
                    or not isinstance(username, str) or not username.strip()
                    or self._session is None):
                raise D2MalformedAuthentication()
            self._session.authenticate(password, username=username, timeout=20.0, stop_event=stop_event)
        except D2AuthenticationRejected:
            failure = AuthenticationFailure.REJECTED
        except D2Cancelled:
            failure = AuthenticationFailure.CANCELLED
        except (D2Timeout, TimeoutError):
            failure = AuthenticationFailure.TIMEOUT
        except D2Unreachable:
            failure = AuthenticationFailure.UNREACHABLE
        except D2ConnectionError:
            failure = AuthenticationFailure.CONNECTION
        except Exception:
            failure = AuthenticationFailure.MALFORMED
        finally:
            password = ""
            username = ""
        if failure is not None:
            raise AuthenticationError(failure) from None
        return self.get_device_state(stop_event=stop_event)

    def get_device_state(self, *, stop_event: Event | None = None) -> DeviceState:
        _check_cancelled(stop_event)
        state = self._client.get_device_state(timeout=20.0, stop_event=stop_event)
        _check_cancelled(stop_event)
        return state

    def is_authenticated(self) -> bool:
        return self._session is not None and self._session.is_authenticated()

    def invalidate_session(self) -> None:
        """Forget local authorization while keeping explicit sign-in usable."""
        if self._session is not None:
            self._session.invalidate()

    def close(self) -> None:
        """Discard authorization and cancel owned router work on shutdown."""
        if self._session is not None:
            self._session.close()


class DemoDeviceService:
    """Explicit offline fixture provider; never falls back to live I/O."""

    is_demo = True

    def get_device_state(self, *, stop_event: Event | None = None) -> DeviceState:
        _check_cancelled(stop_event)
        state = load_demo_state()
        _check_cancelled(stop_event)
        return state
