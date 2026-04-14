from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_ZONE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "defended_zones.json"


def _safe_string(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _safe_number(value: Any, fallback: float) -> float:
    return float(value) if isinstance(value, (int, float)) else fallback


def default_zones() -> list[dict[str, Any]]:
    return [
        {
            "id": "ZONE-BASE",
            "name": "Base",
            "type": "BASE",
            "position": {"x": 0.0, "y": 0.0},
            "radius_m": 700.0,
            "priority": 100,
            "health": 100,
            "status": "SECURE",
        },
        {
            "id": "ZONE-AIRPORT",
            "name": "Airport",
            "type": "AIRPORT",
            "position": {"x": 2200.0, "y": -1400.0},
            "radius_m": 850.0,
            "priority": 85,
            "health": 100,
            "status": "SECURE",
        },
        {
            "id": "ZONE-CITY",
            "name": "City",
            "type": "CITY",
            "position": {"x": -2600.0, "y": 1900.0},
            "radius_m": 1200.0,
            "priority": 70,
            "health": 100,
            "status": "SECURE",
        },
    ]


def normalize_zone(raw_zone: dict[str, Any], index: int) -> dict[str, Any]:
    position = raw_zone.get("position", {}) if isinstance(raw_zone.get("position"), dict) else {}
    health = max(0, min(100, int(_safe_number(raw_zone.get("health"), 100))))
    status = "LOST" if health <= 0 else ("DAMAGED" if health < 100 else "SECURE")
    return {
        "id": _safe_string(raw_zone.get("id"), f"ZONE-{index + 1}"),
        "name": _safe_string(raw_zone.get("name"), f"Zone {index + 1}"),
        "type": _safe_string(raw_zone.get("type"), "ZONE").upper(),
        "position": {
            "x": _safe_number(position.get("x"), 0.0),
            "y": _safe_number(position.get("y"), 0.0),
        },
        "radius_m": max(50.0, _safe_number(raw_zone.get("radius_m"), 500.0)),
        "priority": max(0, int(_safe_number(raw_zone.get("priority"), 50))),
        "health": health,
        "status": status,
    }


def load_defended_zones(config_path: Path | None = None) -> list[dict[str, Any]]:
    config_file = config_path or DEFAULT_ZONE_CONFIG_PATH
    try:
        payload = json.loads(config_file.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default_zones()

    raw_zones = payload.get("zones")
    if not isinstance(raw_zones, list) or not raw_zones:
        return default_zones()

    normalized = [normalize_zone(zone, index) for index, zone in enumerate(raw_zones) if isinstance(zone, dict)]
    return normalized or default_zones()
