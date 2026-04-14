from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class HostileTemplate:
    track_id: str
    type: str
    iff: str
    initial_range_m: float
    altitude_m: float
    speed_mps: float
    angle_offset_rad: float
    approach_rate_mps: float
    orbit_rate_rad: float
    priority_bias: int = 0
    heading_offset_deg: float = 0.0
    alive_until_tick: int | None = None


@dataclass(frozen=True)
class ScenarioDefinition:
    name: str
    time_limit_s: int
    templates: tuple[HostileTemplate, ...]

    def generate_tracks(self, tick: int) -> list[dict]:
        tracks = []
        for index, template in enumerate(self.templates):
            range_m = max(0.0, template.initial_range_m - (tick * template.approach_rate_mps))
            angle = template.angle_offset_rad + (tick * template.orbit_rate_rad)
            hostile = template.iff == "HOSTILE"
            alive = template.alive_until_tick is None or tick <= template.alive_until_tick
            priority_bonus = {
                "BALLISTIC_MISSILE": 18,
                "CRUISE_MISSILE": 12,
                "MISSILE": 10,
            }.get(template.type, 0)
            priority = 95 - (index * 8) + priority_bonus
            priority += int(template.priority_bias)

            tracks.append(
                {
                    "id": template.track_id,
                    "type": template.type,
                    "range_m": round(range_m, 1),
                    "altitude_m": round(template.altitude_m, 1),
                    "speed_mps": template.speed_mps,
                    "priority": max(5, min(100, priority)),
                    "priority_bias": int(template.priority_bias),
                    "iff": template.iff,
                    "engagement_state": "OBSERVED" if hostile else "MONITOR",
                    "position": {
                        "x": round(math.cos(angle) * range_m, 1),
                        "y": round(math.sin(angle) * range_m, 1),
                    },
                    "heading_deg": int((math.degrees(angle) + template.heading_offset_deg) % 360),
                    "alive": alive,
                }
            )
        return tracks
