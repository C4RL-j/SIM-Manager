"""Home-only date typography and a static connection mark."""

from datetime import datetime
import re

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from sim_manager.account_models import AccountData
from sim_manager.services.presentation import present_promo_expiry


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_REPORTED_DATE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"(?:[ T](?P<time>[0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,6})?)?)"
    r"(?P<offset>Z|[+-](?P<zone_hour>[0-9]{2}):?(?P<zone_minute>[0-9]{2}))?)?\Z"
)


def _calendar(value: datetime) -> str:
    return f"{_MONTHS[value.month - 1]} {value.day}, {value.year:04d}"


def _clock(value: datetime, *, seconds: bool = False) -> str:
    clock = f"{value.hour % 12 or 12}:{value.minute:02d}"
    if seconds and (value.second or value.microsecond):
        clock += f":{value.second:02d}"
        if value.microsecond:
            clock += f".{value.microsecond:06d}".rstrip("0")
    return clock + (" AM" if value.hour < 12 else " PM")


def _offset(value: datetime) -> str:
    offset = value.strftime("%z")
    if not offset:
        return ""
    return " UTC" if offset == "+0000" else f" UTC{offset[:3]}:{offset[3:5]}"


def format_reported_date(value: str | None) -> str:
    """Format recognized dates without assigning or converting a carrier zone."""
    if value is None or type(value) is not str:
        return "Not available"
    match = _REPORTED_DATE.fullmatch(value)
    if match is None:
        return value
    if (match.group("zone_hour") is not None
            and (int(match.group("zone_hour")) > 23 or int(match.group("zone_minute")) > 59)):
        return value
    try:
        reported = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError):
        return value
    label = _calendar(reported)
    if match.group("time") is not None:
        label += " · " + _clock(reported, seconds=True)
        zone = match.group("offset")
        if zone == "Z":
            label += " UTC"
        elif zone is not None:
            label += f" UTC{zone[:3]}:{zone[-2:]}"
    return label


def format_promo_expiry(data: AccountData | None) -> str:
    """Format neutral dates, keeping labels for multiple associations."""
    lines = present_promo_expiry(data).splitlines()
    if (isinstance(data, AccountData) and not data.active_promos
            and len(data.data_buckets) == 1 and len(lines) == 1):
        prefix = data.data_buckets[0].name + ": "
        if lines[0].startswith(prefix):
            # The adjacent bucket label already supplies this one association.
            lines[0] = lines[0][len(prefix):]
    rows = []
    for line in lines:
        name, separator, date = line.rpartition(": ")
        rows.append(name + separator + format_reported_date(date)
                    if separator else format_reported_date(line))
    return "\n".join(rows)


def format_last_updated(value: datetime) -> str:
    """Show a successful aware timestamp in the PC's local calendar."""
    if not isinstance(value, datetime):
        return ""
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            return ""
        local = value.astimezone()
        return "Last updated: " + _calendar(local) + " · " + _clock(local) + _offset(local)
    except (ValueError, OverflowError, OSError):
        return ""


def connection_icon(color: str | QColor) -> QIcon:
    """Draw the same antenna arcs in every state, without implying strength."""
    try:
        ink = QColor(color)
    except (TypeError, ValueError):
        ink = QColor("#97a8ba")
    if not ink.isValid():
        ink = QColor("#97a8ba")
    icon = QIcon()
    for ratio in (1, 2, 3):
        pixmap = QPixmap(20 * ratio, 20 * ratio)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(ink, 1.5, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        for rectangle in (QRectF(2, 0, 16, 16), QRectF(6, 4, 8, 8)):
            painter.drawArc(rectangle, -45 * 16, 90 * 16)
            painter.drawArc(rectangle, 135 * 16, 90 * 16)
        painter.drawEllipse(QRectF(9, 7, 2, 2))
        mast = QPainterPath()
        mast.moveTo(10, 10)
        mast.lineTo(7, 17)
        mast.lineTo(13, 17)
        mast.closeSubpath()
        mast.moveTo(8.3, 14)
        mast.lineTo(11.7, 14)
        painter.drawPath(mast)
        painter.end()
        icon.addPixmap(pixmap)
    return icon
