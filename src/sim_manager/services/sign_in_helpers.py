"""Private, explicit sign-in helpers over normalized SIM/SMS values only.

The first complete inbox after an SMS request is a conservative baseline, not
an OTP offer. Subsequent newly observed content can offer one likely DITO code;
this proves neither SMS authenticity nor binding to the number entered on site.
No inbox, message body, sender, router timestamp or message ID is retained.
"""

from __future__ import annotations

from hashlib import sha256
import math
import time
from typing import Callable

from sim_manager.carriers.dito import DitoOtpCandidate, match_otp
from sim_manager.message_models import Message, MessageInbox


def mydito_number(number: str) -> str:
    """Copy formatting only: remove one first leading zero, without mutation."""
    if type(number) is not str:
        return ""
    return number[1:] if number.startswith("0") else number


class NewMessageOtpWatch:
    """A bounded, memory-only likely-OTP watch with no retrieval or submission.

    A different newly observed code makes the request ambiguous until the user
    explicitly requests again. Earlier requests' content stays excluded, even
    when router IDs or timestamps change. Call ``cancel`` on context/session
    changes and disposal to release all private state.
    """

    _MAX_FINGERPRINTS = 1024
    _MAX_OBSERVATIONS = 256

    def __init__(
        self, *, clock: Callable[[], float] = time.monotonic,
        max_age: float = 300.0,
    ) -> None:
        if (type(max_age) not in (int, float) or not 0 < max_age <= 300
                or not math.isfinite(max_age)):
            raise ValueError("Invalid OTP helper lifetime.")
        self._clock = clock
        self._max_age = max_age
        self._deadline: float | None = None
        self._baseline = False
        self._excluded: set[bytes] = set()
        self._seen: set[bytes] = set()
        self._candidate: DitoOtpCandidate | None = None
        self._ambiguous = False
        self._blocked = False
        self._observations = 0

    def __repr__(self) -> str:
        return "NewMessageOtpWatch(<details omitted>)"

    def _now(self) -> float | None:
        try:
            now = self._clock()
            if type(now) in (int, float) and math.isfinite(now):
                return now
        except Exception:
            pass
        return None

    def _expire(self) -> bool:
        now = self._now()
        if self._deadline is None or now is None or now >= self._deadline:
            self._deadline = None
            self._candidate = None
            self._baseline = False
            return True
        return False

    @property
    def active(self) -> bool:
        return not self._expire()

    @property
    def available(self) -> bool:
        return self.active and self._candidate is not None

    def start_request(self) -> None:
        """Begin a new user-requested window; no existing candidate survives."""
        self._excluded.update(self._seen)
        self._seen.clear()
        self._candidate = None
        self._baseline = False
        self._ambiguous = False
        self._observations = 0
        now = self._now()
        self._deadline = (
            now + self._max_age if now is not None and not self._blocked else None
        )

    @staticmethod
    def _matches(
        inbox: MessageInbox,
    ) -> list[tuple[bytes, DitoOtpCandidate]] | None:
        if (not isinstance(inbox, MessageInbox) or inbox.available is not True
                or inbox.partial is not False or type(inbox.messages) is not tuple
                or type(inbox.issues) is not tuple or inbox.issues):
            return None
        matches: list[tuple[bytes, DitoOtpCandidate]] = []
        for message in inbox.messages:
            if (not isinstance(message, Message) or type(message.body) is not str
                    or message.sender is not None and type(message.sender) is not str):
                return None
            candidate = match_otp(message)
            if candidate is None:
                continue
            # Sender is already verified as DITO by the carrier matcher. Ignore
            # ID/time completely; normalize sender spelling, preserve body.
            fingerprint = sha256(
                b"sim-manager:otp-content:v1\0DITO\0"
                + message.body.encode("utf-8", errors="surrogatepass")
            ).digest()
            matches.append((fingerprint, candidate))
        return matches

    def observe(self, inbox: MessageInbox) -> bool:
        """Offer only content arriving after one complete post-request baseline."""
        if not self.active:
            return False
        self._observations += 1
        oversized = (
            isinstance(inbox, MessageInbox) and type(inbox.messages) is tuple
            and len(inbox.messages) > self._MAX_FINGERPRINTS
        )
        if self._observations > self._MAX_OBSERVATIONS or oversized:
            self._blocked = True
            self._deadline = None
            self._candidate = None
            return False
        matches = self._matches(inbox)
        if matches is None:
            # Unknown/partial reads provide no evidence; preserve an already
            # proven candidate until its bounded deadline, but never add one.
            return self.available
        fingerprints = {fingerprint for fingerprint, _ in matches}
        if len(self._excluded | self._seen | fingerprints) > self._MAX_FINGERPRINTS:
            self._blocked = True
            self._deadline = None
            self._candidate = None
            return False
        self._seen.update(fingerprints)
        if not self._baseline:
            self._excluded.update(fingerprints)
            self._baseline = True
            return False
        if not self._ambiguous:
            for fingerprint, candidate in matches:
                if fingerprint in self._excluded:
                    continue
                if self._candidate is None:
                    self._candidate = candidate
                elif candidate.copy_value() != self._candidate.copy_value():
                    self._candidate = None
                    self._ambiguous = True
                    break
        return self.available

    def value(self) -> str | None:
        """Return private code only for an explicit Fill OTP or Copy OTP action."""
        return self._candidate.copy_value() if self.available else None

    def cancel(self) -> None:
        self._deadline = None
        self._baseline = False
        self._excluded.clear()
        self._seen.clear()
        self._candidate = None
        self._ambiguous = False
        self._blocked = False
        self._observations = 0
