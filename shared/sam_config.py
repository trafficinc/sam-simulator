from __future__ import annotations

import json
from pathlib import Path
from typing import Any


JsonDict = dict[str, Any]


DEFAULT_SAM_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "sam_batteries.json"
)


def default_sam_batteries() -> list[JsonDict]:
    return [
        {
            "id": "BTRY-A",
            "name": "Battery A",
            "position": {"x": 0.0, "y": 0.0},
            "max_range_m": 4500.0,
            "ammo": 8,
            "max_channels": 2,
            "status": "READY",
        }
    ]


def normalize_sam_battery(raw: JsonDict, fallback_index: int) -> JsonDict:
    battery_id = str(raw.get("id") or f"BTRY-{fallback_index}")
    name = str(raw.get("name") or battery_id)
    position = raw.get("position", {})
    x = float(position.get("x", 0.0))
    y = float(position.get("y", 0.0))
    max_range_m = max(1000.0, float(raw.get("max_range_m", 4500.0)))
    ammo = max(0, int(raw.get("ammo", 8)))
    max_channels = max(1, int(raw.get("max_channels", 2)))
    status = str(raw.get("status") or "READY").upper()
    return {
        "id": battery_id,
        "name": name,
        "position": {"x": x, "y": y},
        "max_range_m": max_range_m,
        "ammo": ammo,
        "max_channels": max_channels,
        "status": status,
    }


def load_sam_batteries(config_path: Path | None = None) -> list[JsonDict]:
    path = config_path or DEFAULT_SAM_CONFIG_PATH
    try:
        raw = json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default_sam_batteries()

    batteries = raw.get("batteries")
    if not isinstance(batteries, list) or not batteries:
        return default_sam_batteries()

    normalized = []
    for index, item in enumerate(batteries, start=1):
        if isinstance(item, dict):
            normalized.append(normalize_sam_battery(item, index))

    return normalized or default_sam_batteries()
