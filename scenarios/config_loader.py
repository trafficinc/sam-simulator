from __future__ import annotations

import json
from pathlib import Path

from scenarios.base import HostileTemplate, ScenarioDefinition
from scenarios.default_layered_raid import SCENARIO as DEFAULT_LAYERED_RAID
from scenarios.group_saturation_raid import SCENARIO as GROUP_SATURATION_RAID


DEFAULT_SCENARIO_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config" / "scenarios"
FALLBACK_SCENARIOS = {
    DEFAULT_LAYERED_RAID.name: DEFAULT_LAYERED_RAID,
    GROUP_SATURATION_RAID.name: GROUP_SATURATION_RAID,
}


def load_scenarios(config_dir: Path | None = None) -> dict[str, ScenarioDefinition]:
    scenario_dir = config_dir or DEFAULT_SCENARIO_CONFIG_DIR
    loaded: dict[str, ScenarioDefinition] = {}
    if scenario_dir.exists():
        for path in sorted(scenario_dir.glob("*.json")):
            scenario = load_scenario_file(path)
            if scenario is not None:
                loaded[scenario.name] = scenario
    if loaded:
        return loaded
    return dict(FALLBACK_SCENARIOS)


def load_scenario_file(path: Path) -> ScenarioDefinition | None:
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None

    name = str(raw.get("name") or path.stem).strip()
    if not name:
        return None
    time_limit_s = max(1, int(raw.get("time_limit_s", 180)))
    raw_templates = raw.get("templates")
    if not isinstance(raw_templates, list) or not raw_templates:
        return None

    templates: list[HostileTemplate] = []
    for item in raw_templates:
        if not isinstance(item, dict):
            continue
        track_id = str(item.get("track_id", "")).strip()
        track_type = str(item.get("type", "UNKNOWN")).strip().upper()
        iff = str(item.get("iff", "UNKNOWN")).strip().upper()
        if not track_id:
            continue
        alive_until_tick = item.get("alive_until_tick")
        templates.append(
            HostileTemplate(
                track_id=track_id,
                type=track_type,
                iff=iff,
                initial_range_m=float(item.get("initial_range_m", 5000.0)),
                altitude_m=float(item.get("altitude_m", 2500.0)),
                speed_mps=float(item.get("speed_mps", 0.0)),
                angle_offset_rad=float(item.get("angle_offset_rad", 0.0)),
                approach_rate_mps=float(item.get("approach_rate_mps", 0.0)),
                orbit_rate_rad=float(item.get("orbit_rate_rad", 0.0)),
                priority_bias=int(item.get("priority_bias", 0)),
                heading_offset_deg=float(item.get("heading_offset_deg", 0.0)),
                alive_until_tick=int(alive_until_tick) if alive_until_tick is not None else None,
            )
        )

    if not templates:
        return None

    return ScenarioDefinition(
        name=name,
        time_limit_s=time_limit_s,
        templates=tuple(templates),
    )
