"""Desktop display strings from normalized device and account values."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re

from sim_manager.account_models import AccountData
from sim_manager.devices.d2.status_parser import SOURCE_KEYS
from sim_manager.models import (
    Availability, ConnectionMode, ConnectionState, DeviceIssue, DeviceState,
    IssueCode, NetworkState, PinState, RadioState, Readiness, SimState, WanState,
)


@dataclass(frozen=True, slots=True, repr=False)
class DeviceView:
    sim_state: str
    pin: str
    network_mode: str
    network_status: str
    carrier: str
    rsrp: str
    secondary_rsrp: str
    rsrq: str
    rssi: str
    sinr: str
    bands: str
    wan_state: str
    address: str
    router_status: str
    notice: str
    level: str

    def __repr__(self) -> str:
        return "DeviceView(<details omitted>)"


def _connection(value: object) -> str:
    if type(value) is ConnectionState:
        if value is ConnectionState.CONNECTED:
            return "Connected"
        if value is ConnectionState.DISCONNECTED:
            return "Disconnected"
    return "Unknown"


def _number(value: object) -> str:
    if type(value) not in (int, float):
        return "—"
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return "—"
    if not math.isfinite(number) or abs(number) >= 1000:
        return "—"
    return str(int(number)) if number.is_integer() else str(number)


def _bands(value: object) -> str:
    if type(value) is not tuple or not value or len(value) > 128:
        return "—"
    if any(type(band) is not int or not 1 <= band <= 999 for band in value):
        return "—"
    text = " / ".join(str(band) for band in value)
    return text if len(text) <= 256 else "—"


def _address(value: object) -> str:
    if type(value) is Availability:
        if value is Availability.AVAILABLE:
            return "Reported"
        if value is Availability.UNAVAILABLE:
            return "Not reported"
    return "Unknown"


_DATA_QUANTITY = re.compile(
    r"-?(?:[0-9]{1,16}|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]{1,8})? "
    r"(?:B|[KMGTPEZY]B|[KMGTPEZY]iB|kB)\Z"
)


def present_promo_expiry(data: AccountData | None) -> str:
    """Preserve reported promo/data-bucket dates without selecting a total.

    AccountData.expiry describes the load balance and is never a promo date.
    Unclassified and unlimited buckets lack data-unit evidence, so their names
    cannot establish that an expiry belongs to a data allowance.
    """
    if not isinstance(data, AccountData):
        return "Not available"
    if any(promo.expiry is not None for promo in data.active_promos):
        if len(data.active_promos) == 1:
            return data.active_promos[0].expiry
        return "\n".join(
            f"{promo.name}: {promo.expiry or 'Not available'}"
            for promo in data.active_promos
        )
    buckets = tuple(
        bucket for bucket in data.data_buckets
        if type(bucket.remaining) is str and _DATA_QUANTITY.fullmatch(bucket.remaining)
    )
    if not any(bucket.expiry is not None for bucket in buckets):
        return "Not available"
    return "\n".join(
        f"{bucket.name}: {bucket.expiry or 'Not available'}"
        for bucket in buckets
    )


def present_device(state: DeviceState) -> DeviceView:
    """Emit fixed literals and bounded numbers, never arbitrary model text.

    Enum values must be real members, not strings that compare equal to them.
    A Connected network label does not establish successful router retrieval.
    """
    if not isinstance(state, DeviceState):
        state = DeviceState()
        invalid_state = True
    else:
        invalid_state = False
    sim = state.sim if isinstance(state.sim, SimState) else SimState()
    network = state.network if isinstance(state.network, NetworkState) else NetworkState()
    radio = state.radio if isinstance(state.radio, RadioState) else RadioState()
    wan = state.wan if isinstance(state.wan, WanState) else WanState()

    pin = "Unknown"
    if type(sim.pin_state) is PinState and sim.pin_state is PinState.PIN_REQUIRED:
        pin = "PIN required"
    elif type(sim.pin_state) is PinState and sim.pin_state is PinState.PUK_REQUIRED:
        pin = "PUK required"
    elif sim.pin_check_enabled is False:
        pin = "Off"
    elif sim.pin_check_enabled is True:
        pin = "On"

    sim_state = "Unknown"
    if sim.present is False or (
        type(sim.pin_state) is PinState
        and sim.pin_state in (PinState.PIN_REQUIRED, PinState.PUK_REQUIRED)
    ):
        sim_state = "Not Ready"
    elif (type(sim.readiness) is Readiness and sim.readiness is Readiness.READY
          and (sim.present is None or sim.present is True)
          and type(sim.pin_state) is PinState):
        sim_state = "Ready"

    sources = state.successful_sources
    valid_sources = (
        type(sources) is tuple and len(sources) <= len(SOURCE_KEYS)
        and all(type(source) is str and source in SOURCE_KEYS for source in sources)
        and len(set(sources)) == len(sources)
    )
    has_success = bool(sources) if valid_sources else False
    codes: set[IssueCode] = set()
    unknown_error = invalid_state or not valid_sources or type(state.partial) is not bool
    if type(state.errors) is tuple:
        for issue in state.errors:
            if isinstance(issue, DeviceIssue) and type(issue.code) is IssueCode:
                codes.add(issue.code)
            else:
                unknown_error = True
    else:
        unknown_error = True
    incomplete = state.partial is not False or not valid_sources or len(sources) < len(SOURCE_KEYS)

    if IssueCode.CANCELLED in codes:
        notice, level = "Refresh cancelled", "info"
    elif IssueCode.AUTHENTICATION_REQUIRED in codes:
        notice, level = "Authentication required", "warning"
    elif IssueCode.UNREACHABLE in codes:
        notice, level = "Router unreachable", "warning" if has_success else "error"
    elif IssueCode.CONNECTION_ERROR in codes:
        notice, level = "Router connection problem", "warning" if has_success else "error"
    elif IssueCode.MALFORMED_RESPONSE in codes:
        notice, level = "Malformed response", "warning" if has_success else "error"
    elif IssueCode.UNAVAILABLE in codes or IssueCode.TIMEOUT in codes:
        notice, level = "Router status unavailable", "warning" if has_success else "error"
    elif unknown_error:
        notice, level = "Unknown error", "error"
    elif has_success and incomplete:
        notice, level = "Partial device data", "warning"
    elif not has_success:
        notice, level = "Router status unavailable", "warning"
    else:
        notice, level = "", "ok"

    if has_success:
        router_status = "Partial data" if incomplete or codes or unknown_error else "Status available"
    elif IssueCode.AUTHENTICATION_REQUIRED in codes:
        router_status = "Authentication required"
    else:
        router_status = "Router status unavailable"

    return DeviceView(
        sim_state=sim_state,
        pin=pin,
        network_mode="LTE" if type(network.connection_mode) is ConnectionMode and network.connection_mode is ConnectionMode.LTE else "Unknown",
        network_status=_connection(network.connection),
        carrier="Unknown",
        rsrp=_number(radio.rsrp),
        secondary_rsrp=_number(radio.secondary_rsrp),
        rsrq=_number(radio.rsrq),
        rssi=_number(radio.rssi),
        sinr=_number(radio.sinr),
        bands=_bands(radio.bands),
        wan_state=_connection(wan.connection),
        address=_address(wan.address_availability),
        router_status=router_status,
        notice=notice,
        level=level,
    )
