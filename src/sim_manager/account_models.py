"""Carrier-neutral account values; diagnostic output omits all fields."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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


class AccountDataIssue(str, Enum):
    """Closed data outcomes without response bodies or private error text."""

    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    EXPIRED = "expired"
    ACCOUNT_MISMATCH = "account_mismatch"
    RATE_LIMITED = "rate_limited"


MAX_ACCOUNT_RETRY_SECONDS = 3600


def _account_text(value: object, *, optional: bool = False, limit: int = 160) -> bool:
    if value is None:
        return optional
    return (type(value) is str and 1 <= len(value) <= limit
            and bool(value.strip())
            and not any(ord(char) < 32 or ord(char) == 127
                        or 0xD800 <= ord(char) <= 0xDFFF for char in value))


def _invalid_account_data() -> None:
    raise ValueError("Account data is invalid.")


@dataclass(frozen=True, slots=True, repr=False)
class AccountPromo:
    name: str
    expiry: str | None = None

    def __post_init__(self) -> None:
        if not _account_text(self.name) or not _account_text(self.expiry, optional=True):
            _invalid_account_data()

    def __repr__(self) -> str:
        return "AccountPromo(<details omitted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AccountBucket:
    name: str
    remaining: str | None = None
    expiry: str | None = None

    def __post_init__(self) -> None:
        if (not _account_text(self.name)
                or not _account_text(self.remaining, optional=True)
                or not _account_text(self.expiry, optional=True)):
            _invalid_account_data()

    def __repr__(self) -> str:
        return "AccountBucket(<details omitted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AccountData:
    """Reported display values, with no inferred total or private identifiers."""

    updated_at: datetime
    load_balance: str | None = None
    data_remaining: str | None = None
    active_promos: tuple[AccountPromo, ...] = ()
    expiry: str | None = None
    sms_allowance: str | None = None
    call_allowance: str | None = None
    data_buckets: tuple[AccountBucket, ...] = ()
    source: str = "official MyDITO"

    def __post_init__(self) -> None:
        valid_time = (type(self.updated_at) is datetime
                      and self.updated_at.tzinfo is not None
                      and self.updated_at.utcoffset() is not None)
        valid_values = all(_account_text(value, optional=True) for value in (
            self.load_balance, self.data_remaining, self.expiry,
            self.sms_allowance, self.call_allowance,
        ))
        valid_promos = (type(self.active_promos) is tuple
                        and len(self.active_promos) <= 64
                        and all(type(item) is AccountPromo for item in self.active_promos))
        valid_buckets = (type(self.data_buckets) is tuple
                         and len(self.data_buckets) <= 128
                         and all(type(item) is AccountBucket for item in self.data_buckets))
        if (not valid_time or not valid_values or not valid_promos
                or not valid_buckets or self.source != "official MyDITO"):
            _invalid_account_data()

    def __repr__(self) -> str:
        return "AccountData(<details omitted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AccountDataResult:
    data: AccountData | None = None
    issue: AccountDataIssue | None = None
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.retry_after_seconds is not None and (
            self.issue is not AccountDataIssue.RATE_LIMITED
            or type(self.retry_after_seconds) is not int
            or not 1 <= self.retry_after_seconds <= MAX_ACCOUNT_RETRY_SECONDS
        ):
            _invalid_account_data()

    def __repr__(self) -> str:
        return "AccountDataResult(<details omitted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AccountState:
    phase: AccountPhase = AccountPhase.DISCONNECTED
    validity: SessionValidity = SessionValidity.UNKNOWN
    issue: AccountIssue | None = None
    otp_available: bool = False
    is_demo: bool = False
    data: AccountData | None = None
    data_refreshing: bool = False
    data_stale: bool = False
    data_issue: AccountDataIssue | None = None
    retry_after_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.retry_after_seconds is not None and (
            self.data_issue is not AccountDataIssue.RATE_LIMITED
            or type(self.retry_after_seconds) is not int
            or not 1 <= self.retry_after_seconds <= MAX_ACCOUNT_RETRY_SECONDS
        ):
            _invalid_account_data()

    def __repr__(self) -> str:
        return "AccountState(<details omitted>)"
