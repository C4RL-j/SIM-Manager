"""Normalize verified D2 status shapes without retaining raw/private values.

Inputs are parsed HTTP JSON envelopes, not the development probe's filtered
report. Field presence, retrieval completeness, and known status labels are
separate from identifier validity, registration, carrier identity, and units.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import math
import re

from sim_manager.models import (
    Availability,
    CarrierEvidence,
    ConnectionMode,
    ConnectionState,
    DeviceIssue,
    DeviceState,
    IssueCode,
    NetworkState,
    RadioState,
    Readiness,
    SimState,
    WanState,
)

SOURCE_KEYS = ('wireless', 'internet', 'wan', 'device', 'wanStatus', 'sim', 'deviceDetails')
_SIGNAL_TEXT = re.compile(r'[+-]?[0-9]{1,3}(?:\.[0-9]{1,6})?\Z')
_PLACEHOLDERS = frozenset({
    'masked', 'omitted', 'redacted', 'unknown', 'n/a', 'na', 'null', 'none',
    'undefined', '-', '--',
})


def _sim_identity(value: object) -> str | None:
    """Conservative ICCID syntax/check digit, not issuer or ownership proof.

    Accept only unmasked 19/20-digit telecom identifiers. The raw value lives
    only in the response parsing frame and never enters the device snapshot.
    """
    if not isinstance(value, str) or re.fullmatch(r"89[0-9]{17,18}", value) is None:
        return None
    total = 0
    for index, char in enumerate(reversed(value)):
        digit = ord(char) - ord("0")
        if index % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    if total % 10:
        return None
    digest = hashlib.sha256(b"sim-manager:sim-iccid:v1\x00" + value.encode("ascii")).hexdigest()
    return "iccid-v1:" + digest


def _reported_phone(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text if re.fullmatch(r"\+?[0-9]{7,15}", text) else None


def _populated(*values: object) -> object:
    """An explicit unfamiliar state must not become a stale fallback Ready."""
    for value in values:
        if value is None or isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _label(value: object) -> str | None:
    return value.strip() if isinstance(value, str) else None


def _availability(*values: object) -> Availability:
    """Describe the first reported text; never copy or validate its contents."""
    for value in values:
        if not isinstance(value, str):
            continue
        text = value.strip()
        if not text:
            return Availability.UNAVAILABLE
        if (
            text.lower() in _PLACEHOLDERS
            or re.search(r'\b(?:masked|omitted|redacted)\b', text, re.IGNORECASE)
            or '*' in text or '\u2022' in text
            or re.fullmatch(r'[xX]+', text)
        ):
            return Availability.UNKNOWN
        return Availability.AVAILABLE
    return Availability.UNKNOWN


def _signal(value: object) -> float | None:
    if type(value) in (int, float):
        try:
            number = float(value)
        except (ValueError, OverflowError):
            return None
    elif isinstance(value, str) and _SIGNAL_TEXT.fullmatch(value.strip()):
        number = float(value.strip())
    else:
        return None
    return number if math.isfinite(number) and abs(number) < 1000 else None


def _first_signal(*values: object) -> float | None:
    for value in values:
        number = _signal(value)
        if number is not None:
            return number
    return None


def _bands(value: object) -> tuple[int, ...]:
    if not isinstance(value, str):
        return ()
    text = value.strip()
    # Bound pathological input before integer conversion; no band-role,
    # aggregation, or technology interpretation follows from these numbers.
    if len(text) > 256 or re.fullmatch(r'[0-9]{1,3}(?:/[0-9]{1,3})*', text) is None:
        return ()
    values = tuple(int(part) for part in text.split('/'))
    return values if all(number > 0 for number in values) else ()


def _first_bands(*values: object) -> tuple[int, ...]:
    for value in values:
        bands = _bands(value)
        if bands:
            return bands
    return ()


def _pci(value: object) -> int | None:
    """Bound syntax, not radio validity; Task 004 did not export the PCI value."""
    if type(value) is int:
        return value if 0 <= value <= 999999 else None
    if isinstance(value, str):
        text = value.strip()
        if re.fullmatch(r'[0-9]{1,6}', text):
            return int(text)
    return None


def _safe_issues(errors: tuple[DeviceIssue, ...]) -> list[DeviceIssue]:
    issues = []
    for error in errors:
        if (
            isinstance(error, DeviceIssue) and error.source in SOURCE_KEYS
            and isinstance(error.code, IssueCode)
        ):
            issue = DeviceIssue(source=error.source, code=error.code)
            if issue not in issues:
                issues.append(issue)
    return issues


def normalize_status(
    responses: Mapping[str, object],
    *,
    errors: tuple[DeviceIssue, ...] = (),
    observed_at: datetime | None = None,
) -> DeviceState:
    """Return a carrier-neutral snapshot, tolerating independent field failures.

    An absent endpoint is incomplete retrieval, not a fabricated malformed
    response. A supplied invalid envelope gets a sanitized fixed-source issue.
    Optional missing/unknown fields do not make a valid envelope unsuccessful.
    """
    if not isinstance(responses, Mapping):
        raise TypeError('Status responses must be a mapping.') from None
    data: dict[str, dict] = {}
    issues = _safe_issues(errors)
    for source in SOURCE_KEYS:
        if source not in responses:
            continue
        envelope = responses[source]
        if (
            not isinstance(envelope, dict) or type(envelope.get('code')) is not int
            or envelope['code'] != 200 or not isinstance(envelope.get('data'), dict)
        ):
            issue = DeviceIssue(source=source, code=IssueCode.MALFORMED_RESPONSE)
            if issue not in issues:
                issues.append(issue)
            continue
        data[source] = envelope['data']

    internet = data.get('internet', {})
    wan = data.get('wan', {})
    device = data.get('device', {})
    sim = data.get('sim', {})
    details = data.get('deviceDetails', {})
    raw_connection = data.get('wanStatus', {}).get('ConnectionStatus')
    connection = raw_connection if isinstance(raw_connection, dict) else {}

    ready = _label(_populated(
        sim.get('SIMCardState'), device.get('USIMStatus'), connection.get('USIMStatus')
    ))
    state_label = _label(_populated(connection.get('ConnectStatus'), internet.get('Status')))
    connection_state = {
        'Connected': ConnectionState.CONNECTED,
        'Disconnected': ConnectionState.DISCONNECTED,
    }.get(state_label, ConnectionState.UNKNOWN)

    return DeviceState(
        sim=SimState(
            readiness=Readiness.READY if ready in ('READY', 'Ready') else Readiness.UNKNOWN,
            pin_check_enabled=False if _label(sim.get('PINCheckEnabled')) == 'OFF' else None,
            iccid_availability=_availability(device.get('UICCID')),
            imsi_availability=_availability(
                device.get('IMSI'), connection.get('IMSI'), details.get('IMSI')
            ),
            msisdn_availability=_availability(details.get('MSISDN')),
            identity_key=_sim_identity(device.get('UICCID')),
            phone_number=_reported_phone(details.get('MSISDN')),
        ),
        network=NetworkState(
            connection_mode=(
                ConnectionMode.LTE if _label(connection.get('ConnectMode')) == 'LTE'
                else ConnectionMode.UNKNOWN
            ),
            connection=connection_state,
        ),
        radio=RadioState(
            bands=_first_bands(connection.get('Band'), internet.get('Band')),
            rsrp=_first_signal(connection.get('RSRP0'), internet.get('RSRP')),
            secondary_rsrp=_signal(connection.get('RSRP1')),
            rsrq=_first_signal(connection.get('RSRQ'), internet.get('RSRQ')),
            rssi=_signal(connection.get('RSSI')),
            sinr=_first_signal(connection.get('SINR'), internet.get('SINR')),
            pci=_pci(connection.get('PCI')),
        ),
        wan=WanState(
            connection=connection_state,
            address_availability=_availability(wan.get('IpAddress')),
        ),
        carrier_evidence=CarrierEvidence(),
        observed_at=observed_at if observed_at is not None else datetime.now(timezone.utc),
        successful_sources=tuple(source for source in SOURCE_KEYS if source in data),
        errors=tuple(issues),
        partial=len(data) < len(SOURCE_KEYS) or bool(issues),
    )
