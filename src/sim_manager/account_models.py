"""Carrier-neutral authentication state; diagnostic output omits all fields."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AccountPhase(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    EXPIRED = "expired"
    ERROR = "error"


class SessionValidity(str, Enum):
    UNKNOWN = "unknown"
    VALIDATED = "validated"
    EXPIRED = "expired"


class AccountIssue(str, Enum):
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED_RESPONSE = "unsupported_response"
    EXPIRED = "expired"


class AuthEvent(str, Enum):
    """Closed browser-to-service outcomes; never cookies, tokens or payloads."""

    AUTHENTICATED = "authenticated"
    REJECTED = "rejected"
    EXPIRED = "expired"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    DISCONNECTED = "disconnected"


@dataclass(frozen=True, slots=True, repr=False)
class AccountState:
    phase: AccountPhase = AccountPhase.DISCONNECTED
    validity: SessionValidity = SessionValidity.UNKNOWN
    issue: AccountIssue | None = None
    otp_available: bool = False
    is_demo: bool = False

    def __repr__(self) -> str:
        return "AccountState(<details omitted>)"
