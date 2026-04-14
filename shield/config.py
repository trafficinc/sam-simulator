from __future__ import annotations

import json
import os
from pathlib import Path

from shield.logic import EngagementCapacity, SensorActivation, ShotDoctrine


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "shield.json"


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _env_choice(name: str, default: str, allowed: set[str]) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().upper()
    return normalized if normalized in allowed else default


def _load_file_config() -> dict:
    try:
        if not CONFIG_PATH.exists():
            return {}
        data = json.loads(CONFIG_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _config_int(config: dict, key: str, default: int, minimum: int = 0) -> int:
    value = config.get(key, default)
    if not isinstance(value, int):
        return default
    return max(minimum, value)


def _config_choice(config: dict, key: str, default: str, allowed: set[str]) -> str:
    value = config.get(key, default)
    if not isinstance(value, str):
        return default
    normalized = value.strip().upper()
    return normalized if normalized in allowed else default


def load_sensor_activation() -> SensorActivation:
    config = _load_file_config()
    configured = config.get("active_sensors", ["acoustic", "irst", "radar"])
    default_raw = ",".join(configured) if isinstance(configured, list) and configured else "acoustic,irst,radar"
    raw = os.getenv("SHIELD_ACTIVE_SENSORS", default_raw)
    sensors = [part.strip() for part in raw.split(",")]
    return SensorActivation.from_names(sensors)


def load_capacity() -> EngagementCapacity:
    config = _load_file_config()
    capacity = config.get("capacity", {}) if isinstance(config.get("capacity"), dict) else {}
    return EngagementCapacity(
        missile_channels=_env_int(
            "SHIELD_MISSILE_CHANNELS",
            _config_int(capacity, "missile_channels", 2),
        ),
        jammer_channels=_env_int(
            "SHIELD_JAMMER_CHANNELS",
            _config_int(capacity, "jammer_channels", 1),
        ),
        ciws_channels=_env_int(
            "SHIELD_CIWS_CHANNELS",
            _config_int(capacity, "ciws_channels", 1),
        ),
    )


def load_doctrine() -> ShotDoctrine:
    config = _load_file_config()
    doctrine = config.get("doctrine", {}) if isinstance(config.get("doctrine"), dict) else {}
    allowed = {"SINGLE_SHOT", "SHOT_LOOK_SHOT"}
    return ShotDoctrine(
        missile_mode_high_priority=_env_choice(
            "SHIELD_HIGH_PRIORITY_DOCTRINE",
            _config_choice(doctrine, "high_priority", "SHOT_LOOK_SHOT", allowed),
            allowed,
        ),
        missile_mode_standard=_env_choice(
            "SHIELD_STANDARD_DOCTRINE",
            _config_choice(doctrine, "standard", "SINGLE_SHOT", allowed),
            allowed,
        ),
        hold_fire_below_score=_env_int(
            "SHIELD_HOLD_FIRE_BELOW_SCORE",
            _config_int(doctrine, "hold_fire_below_score", 35, minimum=0),
            minimum=0,
        ),
    )
