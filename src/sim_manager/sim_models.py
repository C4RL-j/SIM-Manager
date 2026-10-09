"""Private SIM profile metadata, separate from router credentials and sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from uuid import UUID

from sim_manager.account_models import AccountState


class SimCarrier(str, Enum):
    UNKNOWN = "unknown"
    DITO = "dito"


class SimProfileValidationError(ValueError):
    def __init__(self) -> None:
        super().__init__("SIM profile details are invalid.")


def valid_identity_key(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"iccid-v1:[0-9a-f]{64}", value) is not None


def normalize_phone_number(value: object) -> str | None:
    """Syntax only: this does not establish ownership, carrier, or SIM identity."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise SimProfileValidationError()
    phone = value.strip()
    if not phone:
        return None
    if re.fullmatch(r"\+?[0-9]{7,15}", phone) is None:
        raise SimProfileValidationError()
    return phone


def normalize_profile_name(value: object) -> str:
    if not isinstance(value, str):
        raise SimProfileValidationError()
    name = value.strip()
    if not 1 <= len(name) <= 80 or any(ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF for char in name):
        raise SimProfileValidationError()
    return name


@dataclass(frozen=True, slots=True, repr=False)
class SimProfile:
    profile_id: str
    name: str
    phone_number: str | None = None
    carrier: SimCarrier = SimCarrier.UNKNOWN
    identity_key: str | None = None
    active: bool = False
    account_state: AccountState = field(default_factory=AccountState)

    def __post_init__(self) -> None:
        identifier = self.profile_id
        valid_id = False
        if isinstance(identifier, str) and len(identifier) == 36:
            try:
                valid_id = str(UUID(identifier)) == identifier
            except ValueError:
                pass
        if not valid_id or not isinstance(self.carrier, SimCarrier) or type(self.active) is not bool or not isinstance(self.account_state, AccountState):
            raise SimProfileValidationError()
        if self.identity_key is not None and not valid_identity_key(self.identity_key):
            raise SimProfileValidationError()
        object.__setattr__(self, "name", normalize_profile_name(self.name))
        object.__setattr__(self, "phone_number", normalize_phone_number(self.phone_number))

    def __repr__(self) -> str:
        return "SimProfile(<details omitted>)"
