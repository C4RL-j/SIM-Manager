"""Reconstruct synthetic raw shapes from the packaged sanitized Task 004 report.

Only retained labels/numbers and literal masked/omitted markers are available.
Hidden values remain unknown; this is neither a raw HTTP capture nor live data.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from importlib.resources import files
import json

from sim_manager.models import DeviceState

from .status_parser import SOURCE_KEYS, normalize_status


def load_demo_state(*, observed_at: datetime | None = None) -> DeviceState:
    """Return one newly normalized offline snapshot marked ``demo:d2``."""
    text = files("sim_manager.resources").joinpath("d2-demo-report.json").read_text(encoding="utf-8")
    report = json.loads(text)["report"]
    responses: dict[str, object] = {}
    for request in report["requests"]:
        source = request["query"]
        if source not in SOURCE_KEYS:
            continue
        summary = request["summary"]
        data: dict[str, object] = {}
        for field_path, field in summary["fields"].items():
            parts = field_path.split(".")
            # All reviewed report fields are strings. Do not turn a hidden
            # marker into guessed content or recover discarded report values.
            if parts[0] != "data" or len(parts) < 2 or field.get("type") != "string":
                continue
            value = field.get("value")
            if not isinstance(value, str):
                continue
            current = data
            for part in parts[1:-1]:
                current = current.setdefault(part, {})
            current[parts[-1]] = value
        responses[source] = {"code": summary["code"], "data": data}
    return replace(normalize_status(responses, observed_at=observed_at), source="demo:d2")
