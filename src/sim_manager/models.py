"""Immutable, carrier-neutral device snapshots with private diagnostic reprs.

Availability describes reported nonempty text, not identifier/address validity.
No raw ICCID/IMSI, credential, address, DNS value, or SMS body is stored here.
The SIM-first profile feature permits a validated reported phone number and a
domain-separated ICCID fingerprint, both omitted from diagnostic repr/str.
Signal measurements deliberately have no asserted units until hardware evidence
establishes them. Explicit serialization of future private fields needs its own
privacy review; repr/str are intentionally opaque.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class Availability(str, Enum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class Readiness(str, Enum):
    UNKNOWN = "unknown"
    READY = "ready"


class PinState(str, Enum):
    UNKNOWN = "unknown"
    PIN_REQUIRED = "pin_required"
    PUK_REQUIRED = "puk_required"


class ConnectionState(str, Enum):
    UNKNOWN = "unknown"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"


class ConnectionMode(str, Enum):
    UNKNOWN = "unknown"
    LTE = "lte"


class IssueCode(str, Enum):
    AUTHENTICATION_REQUIRED = "authentication_required"
    UNREACHABLE = "unreachable"
    CONNECTION_ERROR = "connection_error"
    UNAVAILABLE = "unavailable"
    MALFORMED_RESPONSE = "malformed_response"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class _PrivateRepr:
    """Even accidentally mis-typed constructor arguments stay out of logs."""

    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<details omitted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SimState(_PrivateRepr):
    present: bool | None = None
    readiness: Readiness = Readiness.UNKNOWN
    pin_state: PinState = PinState.UNKNOWN
    pin_check_enabled: bool | None = None
    iccid_availability: Availability = Availability.UNKNOWN
    imsi_availability: Availability = Availability.UNKNOWN
    msisdn_availability: Availability = Availability.UNKNOWN
    identity_key: str | None = None
    phone_number: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class NetworkState(_PrivateRepr):
    connection_mode: ConnectionMode = ConnectionMode.UNKNOWN
    connection: ConnectionState = ConnectionState.UNKNOWN
    operator: str | None = None
    registered: bool | None = None
    roaming: bool | None = None


@dataclass(frozen=True, slots=True, repr=False)
class RadioState(_PrivateRepr):
    bands: tuple[int, ...] = ()
    rsrp: float | None = None
    secondary_rsrp: float | None = None
    rsrq: float | None = None
    rssi: float | None = None
    sinr: float | None = None
    pci: int | None = None
    earfcn: int | None = None
    units_verified: bool = False


@dataclass(frozen=True, slots=True, repr=False)
class WanState(_PrivateRepr):
    connection: ConnectionState = ConnectionState.UNKNOWN
    ip_family: str | None = None
    address_availability: Availability = Availability.UNKNOWN
    apn: str | None = None
    pdp_type: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class CarrierEvidence(_PrivateRepr):
    operator: str | None = None
    plmn: str | None = None
    mcc: str | None = None
    mnc: str | None = None

    @property
    def has_values(self) -> bool:
        return any(value is not None for value in (self.operator, self.plmn, self.mcc, self.mnc))


@dataclass(frozen=True, slots=True, repr=False)
class DeviceIssue(_PrivateRepr):
    # Adapters supply fixed source keys and closed codes, never raw errors.
    source: str
    code: IssueCode


@dataclass(frozen=True, slots=True, repr=False)
class DeviceState(_PrivateRepr):
    sim: SimState = field(default_factory=SimState)
    network: NetworkState = field(default_factory=NetworkState)
    radio: RadioState = field(default_factory=RadioState)
    wan: WanState = field(default_factory=WanState)
    carrier_evidence: CarrierEvidence = field(default_factory=CarrierEvidence)
    observed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "device:d2"
    successful_sources: tuple[str, ...] = ()
    errors: tuple[DeviceIssue, ...] = ()
    # Retrieval completeness, not a claim that every optional field is known.
    partial: bool = True
