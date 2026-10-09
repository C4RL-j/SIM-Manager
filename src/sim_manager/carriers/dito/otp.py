"""Source-evidenced DITO OTP heuristic over a carrier-neutral message.

The legacy sender/phrase rule identifies a likely code, not proven freshness,
account binding, SMS authenticity or a currently verified carrier format.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from sim_manager.message_models import Message


_AUTH_CODE = re.compile(
    r"^\s*([0-9]{6})\s+is your authentication code\.",
    re.IGNORECASE | re.ASCII,
)


@dataclass(frozen=True, slots=True, repr=False)
class DitoOtpCandidate:
    """Private, temporary code available only for an explicit copy action."""

    _code: str

    def __repr__(self) -> str:
        return "DitoOtpCandidate(<details omitted>)"

    def copy_value(self) -> str:
        return self._code


def match_otp(message: Message) -> DitoOtpCandidate | None:
    if not isinstance(message, Message):
        return None
    if type(message.sender) is not str or type(message.body) is not str:
        return None
    if message.sender.strip().upper() != "DITO":
        return None
    match = _AUTH_CODE.match(message.body)
    return DitoOtpCandidate(match.group(1)) if match is not None else None
