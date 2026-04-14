from __future__ import annotations

import math
from dataclasses import dataclass, field

from scenarios.base import ScenarioDefinition


@dataclass
class PilotTrackState:
    track_id: str
    type: str
    iff: str
    initial_range_m: float
    altitude_m: float
    speed_mps: float
    angle_offset_rad: float
    approach_rate_mps: float
    orbit_rate_rad: float
    priority_bias: int
    heading_offset_deg: float
    alive_until_tick: int | None = None
    alive: bool = True
    health: int = 100
    retreating: bool = False
    retreat_start_tick: int | None = None


def _maneuver_amplitude(track_type: str) -> float:
    return {
        "JET": 0.18,
        "HELICOPTER": 0.09,
        "DRONE": 0.06,
    }.get(track_type, 0.0)


def _maneuver_frequency(track_type: str) -> float:
    return {
        "JET": 0.42,
        "HELICOPTER": 0.24,
        "DRONE": 0.32,
    }.get(track_type, 0.0)


def _altitude_variation(track_type: str) -> float:
    return {
        "JET": 220.0,
        "HELICOPTER": 80.0,
        "DRONE": 60.0,
    }.get(track_type, 0.0)


@dataclass
class PilotTruthModel:
    scenario: ScenarioDefinition
    states: dict[str, PilotTrackState] = field(default_factory=dict)
    current_tick: int = 0

    @classmethod
    def from_scenario(cls, scenario: ScenarioDefinition) -> "PilotTruthModel":
        states = {}
        for template in scenario.templates:
            health = (
                100
                if template.type in {"JET", "MISSILE", "CRUISE_MISSILE", "BALLISTIC_MISSILE"}
                else 90 if template.type == "HELICOPTER" else 60
            )
            states[template.track_id] = PilotTrackState(
                track_id=template.track_id,
                type=template.type,
                iff=template.iff,
                initial_range_m=template.initial_range_m,
                altitude_m=template.altitude_m,
                speed_mps=template.speed_mps,
                angle_offset_rad=template.angle_offset_rad,
                approach_rate_mps=template.approach_rate_mps,
                orbit_rate_rad=template.orbit_rate_rad,
                priority_bias=template.priority_bias,
                heading_offset_deg=template.heading_offset_deg,
                alive_until_tick=template.alive_until_tick,
                health=health,
            )
        return cls(scenario=scenario, states=states)

    def apply_snapshot(self, snapshot: dict) -> None:
        for track in snapshot.get("tracks", []):
            state = self.states.get(track.get("id"))
            if state is None:
                continue

            status = track.get("target_status")
            health = track.get("target_health")
            if isinstance(health, (int, float)):
                state.health = max(0, int(health))

            if status in {"NEUTRALIZED", "DESTROYED"}:
                state.alive = False
                continue

            if (
                state.type in {"JET", "HELICOPTER"}
                and state.iff == "HOSTILE"
                and state.health <= 50
                and status in {"HIT", "KILL_ASSESS", "ABORTING"}
                and not state.retreating
                and state.retreat_start_tick is None
            ):
                state.retreat_start_tick = self.current_tick + 3

        for state in self.states.values():
            if state.retreat_start_tick is not None and self.current_tick >= state.retreat_start_tick:
                state.retreating = True

    def generate_tracks(self, tick: int) -> list[dict]:
        self.current_tick = tick
        tracks = []
        for index, state in enumerate(self.states.values()):
            if state.retreat_start_tick is not None and tick >= state.retreat_start_tick:
                state.retreating = True
            if not state.alive:
                continue
            if state.alive_until_tick is not None and tick > state.alive_until_tick:
                continue

            retreat_progress = 0.0
            if state.retreat_start_tick is not None and tick >= state.retreat_start_tick:
                retreat_progress = min(1.0, (tick - state.retreat_start_tick) / 4.0)

            maneuver_phase = tick * _maneuver_frequency(state.type) + (index * 0.7)
            maneuver_offset = math.sin(maneuver_phase) * _maneuver_amplitude(state.type)
            if state.retreating:
                maneuver_offset *= max(0.25, 1.0 - retreat_progress)

            effective_approach = state.approach_rate_mps * (1.0 - (2.0 * retreat_progress))
            if state.retreating and retreat_progress >= 1.0:
                effective_approach = -abs(state.approach_rate_mps)

            range_m = max(0.0, state.initial_range_m - (tick * effective_approach))
            angle = state.angle_offset_rad + (tick * state.orbit_rate_rad) + maneuver_offset
            if retreat_progress > 0.0:
                angle += retreat_progress * 0.85

            hostile = state.iff == "HOSTILE"
            priority_bonus = {
                "BALLISTIC_MISSILE": 18,
                "CRUISE_MISSILE": 12,
                "MISSILE": 10,
            }.get(state.type, 0)
            priority = 95 - (index * 8) + priority_bonus
            priority += int(state.priority_bias)
            base_heading_deg = (math.degrees(angle) + state.heading_offset_deg) % 360
            retreat_heading_deg = (base_heading_deg + 180) % 360
            heading_deg = (base_heading_deg + (180 * retreat_progress)) % 360 if retreat_progress > 0 else base_heading_deg
            if state.retreating and retreat_progress >= 1.0:
                heading_deg = retreat_heading_deg

            altitude_offset = math.cos((tick * 0.3) + (index * 0.5)) * _altitude_variation(state.type)
            if state.retreating:
                altitude_offset *= max(0.3, 1.0 - retreat_progress)
            altitude_m = max(50.0, state.altitude_m + altitude_offset)
            speed_factor = 1.0 - (0.3 * retreat_progress)
            if state.retreating and retreat_progress >= 1.0:
                speed_factor = 0.7

            tracks.append(
                {
                    "id": state.track_id,
                    "type": state.type,
                    "range_m": round(range_m, 1),
                    "altitude_m": round(altitude_m, 1),
                    "speed_mps": round(state.speed_mps * speed_factor, 1),
                    "priority": max(5, min(100, priority)),
                    "priority_bias": int(state.priority_bias),
                    "iff": state.iff,
                    "engagement_state": "RETREAT" if state.retreating else ("OBSERVED" if hostile else "MONITOR"),
                    "maneuver_state": "RETREAT_TURN" if retreat_progress > 0 and retreat_progress < 1.0 else ("RETREAT" if state.retreating else ("INGRESS_MANEUVER" if _maneuver_amplitude(state.type) > 0 else "DIRECT")),
                    "position": {
                        "x": round(math.cos(angle) * range_m, 1),
                        "y": round(math.sin(angle) * range_m, 1),
                    },
                    "heading_deg": int(heading_deg),
                    "alive": True,
                    "health": state.health,
                    "retreating": state.retreating,
                }
            )
        return tracks
