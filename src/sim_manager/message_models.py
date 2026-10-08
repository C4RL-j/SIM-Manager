"""Carrier-neutral, in-memory SMS values with opaque diagnostic output.

Only the Messages UI may display these private fields. Do not serialize them,
log them, or attach them to diagnostic errors. ``timestamp`` is router-reported
text: it asserts neither a timezone nor chronological ordering.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MessageIssueCode(str, Enum):
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    UNREACHABLE = "unreachable"
    AUTHENTICATION_REQUIRED = "authentication_required"
    UNAVAILABLE = "unavailable"
    MALFORMED_RESPONSE = "malformed_response"
    UNSUPPORTED_RESPONSE = "unsupported_response"
    MALFORMED_ENTRY = "malformed_entry"
    DUPLICATE_ID = "duplicate_id"


class _PrivateRepr:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<details omitted>)"


@dataclass(frozen=True, slots=True, repr=False)
class Message(_PrivateRepr):
    """One message; unverified read-state/storage semantics are omitted."""

    identity: str | None = None
    sender: str | None = None
    timestamp: str | None = None
    body: str = ""


@dataclass(frozen=True, slots=True, repr=False)
class MessageInbox(_PrivateRepr):
    """One read result. ``available=False`` must not replace a previous inbox.

    Only an available, non-partial empty tuple proves an explicitly empty inbox
    response. A partial empty tuple means no entries were readable. Partial
    results contain usable entries plus closed issue codes, never raw errors.
    """

    messages: tuple[Message, ...] = ()
    available: bool = True
    partial: bool = False
    issues: tuple[MessageIssueCode, ...] = ()
