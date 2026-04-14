from __future__ import annotations

import math
from dataclasses import dataclass, field

from shared.messages import JsonDict, initial_snapshot, make_event
from shared.sam_config import load_sam_batteries


SPEED_OF_SOUND_MPS = 343.0
DEFAULT_ACTIVE_SENSORS = ("acoustic", "irst", "radar")
FUSION_ORDER = [
    "SILENT",
    "TRIPWIRE",
    "PASSIVE_TRACK",
    "AMBUSH",
    "ACTIVE_TRACK",
    "FIRE",
    "KILL_ASSESS",
]
STATE_RANK = {state: index for index, state in enumerate(FUSION_ORDER)}


@dataclass
class TrackTiming:
    acoustic_entered_at: float | None = None
    acoustic_detected_at: float | None = None
    irst_entered_at: float | None = None
    irst_detected_at: float | None = None
    radar_entered_at: float | None = None
    radar_track_at: float | None = None
    radar_fire_solution_at: float | None = None


@dataclass
class EngagementRecord:
    health: int
    max_health: int
    lifecycle_state: str = "TRACKED"
    assigned_effector: str = "MONITOR"
    assigned_battery: str | None = None
    shot_doctrine: str = "SINGLE_SHOT"
    shots_planned: int = 0
    attempt_count: int = 0
    phase_started_at: float = 0.0


@dataclass(frozen=True)
class SensorActivation:
    acoustic: bool = True
    irst: bool = True
    radar: bool = True

    @classmethod
    def from_names(cls, names: list[str] | tuple[str, ...] | set[str] | None) -> "SensorActivation":
        if not names:
            names = DEFAULT_ACTIVE_SENSORS
        normalized = {name.strip().lower() for name in names if name.strip()}
        return cls(
            acoustic="acoustic" in normalized,
            irst="irst" in normalized,
            radar="radar" in normalized,
        )

    def labels(self) -> list[str]:
        return [
            name
            for name, enabled in (
                ("acoustic", self.acoustic),
                ("irst", self.irst),
                ("radar", self.radar),
            )
            if enabled
        ]


@dataclass(frozen=True)
class EngagementCapacity:
    missile_channels: int = 2
    jammer_channels: int = 1
    ciws_channels: int = 1


@dataclass(frozen=True)
class ShotDoctrine:
    missile_mode_high_priority: str = "SHOT_LOOK_SHOT"
    missile_mode_standard: str = "SINGLE_SHOT"
    hold_fire_below_score: int = 35


@dataclass
class SamBatteryState:
    id: str
    name: str
    position: JsonDict
    max_range_m: float
    ammo_remaining: int
    max_channels: int
    status: str = "READY"

    @classmethod
    def from_config(cls, config: JsonDict) -> "SamBatteryState":
        return cls(
            id=str(config.get("id", "BTRY-A")),
            name=str(config.get("name", config.get("id", "Battery"))),
            position=dict(config.get("position", {"x": 0.0, "y": 0.0})),
            max_range_m=float(config.get("max_range_m", 4500.0)),
            ammo_remaining=int(config.get("ammo", 8)),
            max_channels=int(config.get("max_channels", 2)),
            status=str(config.get("status", "READY")).upper(),
        )


def doctrine_from_mode(mode: str) -> ShotDoctrine:
    normalized = mode.strip().upper()
    if normalized == "AGGRESSIVE":
        return ShotDoctrine(
            missile_mode_high_priority="SHOT_LOOK_SHOT",
            missile_mode_standard="SHOT_LOOK_SHOT",
            hold_fire_below_score=20,
        )
    if normalized == "CONSERVATIVE":
        return ShotDoctrine(
            missile_mode_high_priority="SHOT_LOOK_SHOT",
            missile_mode_standard="SINGLE_SHOT",
            hold_fire_below_score=55,
        )
    return ShotDoctrine(
        missile_mode_high_priority="SHOT_LOOK_SHOT",
        missile_mode_standard="SINGLE_SHOT",
        hold_fire_below_score=35,
    )


def _track_heading_to_base(track: JsonDict) -> bool:
    position = track.get("position", {})
    heading_deg = float(track.get("heading_deg", 0.0))
    x = float(position.get("x", 0.0))
    y = float(position.get("y", 0.0))
    velocity_x = math.cos(math.radians(heading_deg))
    velocity_y = math.sin(math.radians(heading_deg))
    return (x * velocity_x) + (y * velocity_y) < 0


def _heat_factor(track: JsonDict) -> float:
    track_type = track.get("type", "UNKNOWN")
    return {
        "BALLISTIC_MISSILE": 1.1,
        "CRUISE_MISSILE": 0.65,
        "MISSILE": 1.0,
        "JET": 0.9,
        "HELICOPTER": 0.75,
        "DRONE": 0.45,
    }.get(track_type, 0.5)


def _initial_health(track_type: str) -> int:
    return {
        "BALLISTIC_MISSILE": 100,
        "CRUISE_MISSILE": 100,
        "MISSILE": 100,
        "JET": 100,
        "HELICOPTER": 90,
        "DRONE": 60,
    }.get(track_type, 75)


def _is_terminal_status(status: str) -> bool:
    return status in {"DESTROYED", "NEUTRALIZED", "RETREAT"}


def _is_withdrawn_status(status: str) -> bool:
    return status in {"ABORTING", "RETREAT"}


def _abort_threshold(track_type: str) -> int:
    return {
        "JET": 45,
        "HELICOPTER": 50,
    }.get(track_type, 0)


def _deterministic_hit(track: JsonDict, shots_planned: int) -> bool:
    base_threshold = {
        "BALLISTIC_MISSILE": 4,
        "CRUISE_MISSILE": 7,
        "MISSILE": 8,
        "JET": 6,
        "HELICOPTER": 5,
        "DRONE": 4,
    }.get(track.get("type", "UNKNOWN"), 5)
    threshold = min(10, base_threshold + (2 if shots_planned >= 2 else 0))
    roll = sum(ord(char) for char in str(track.get("id", ""))) % 10
    return roll < threshold


def _distance_between(point_a: JsonDict, point_b: JsonDict) -> float:
    dx = float(point_a.get("x", 0.0)) - float(point_b.get("x", 0.0))
    dy = float(point_a.get("y", 0.0)) - float(point_b.get("y", 0.0))
    return math.hypot(dx, dy)


def threat_score(track: JsonDict) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0

    if track.get("iff") != "HOSTILE" or not track.get("alive", True):
        return 0, ["non-hostile or inactive"]

    track_type = track.get("type", "UNKNOWN")
    range_m = float(track.get("range_m", 99999.0))
    speed_mps = float(track.get("speed_mps", 0.0))
    altitude_m = float(track.get("altitude_m", 2500.0))

    type_weights = {
        "BALLISTIC_MISSILE": 100,
        "CRUISE_MISSILE": 50,
        "MISSILE": 95,
        "JET": 80,
        "HELICOPTER": 55,
        "DRONE": 45,
    }
    score += type_weights.get(track_type, 30)
    reasons.append(f"type={track_type}")

    if range_m < 2000:
        score += 35
        reasons.append("inside close-in envelope")
    elif range_m < 4000:
        score += 20
        reasons.append("inside radar/fire-control envelope")
    elif range_m < 7000:
        score += 10
        reasons.append("inside passive tracking envelope")

    if speed_mps > 220:
        score += 15
        reasons.append("high speed")
    elif speed_mps > 120:
        score += 8
        reasons.append("moderate speed")

    if track_type == "CRUISE_MISSILE" and altitude_m < 600:
        score += 10
        reasons.append("low altitude terrain-mask profile")
    if track_type == "BALLISTIC_MISSILE" and altitude_m > 9000:
        score += 18
        reasons.append("high altitude short-reaction profile")

    priority_bias = int(track.get("priority_bias", 0))
    if priority_bias:
        score += priority_bias
        reasons.append(f"priority bias {priority_bias:+d}")

    if _track_heading_to_base(track):
        score += 15
        reasons.append("heading toward protected base")
    else:
        score -= 10
        reasons.append("moving away from base")

    return max(0, min(100, score)), reasons


def track_confidence(track: JsonDict, fusion_state: str, sensor_activation: SensorActivation) -> tuple[int, list[str]]:
    reasons: list[str] = []
    confidence = {
        "SILENT": 0,
        "TRIPWIRE": 35,
        "PASSIVE_TRACK": 58,
        "AMBUSH": 70,
        "ACTIVE_TRACK": 84,
        "FIRE": 95,
        "KILL_ASSESS": 92,
    }.get(fusion_state, 20)
    if fusion_state != "SILENT":
        reasons.append(f"fusion stage {fusion_state}")

    range_m = float(track.get("range_m", 99999.0))
    track_type = str(track.get("type", "UNKNOWN"))
    altitude_m = float(track.get("altitude_m", 2500.0))

    if range_m < 2000:
        confidence += 8
        reasons.append("close-range contact geometry")
    elif range_m > 7000:
        confidence -= 8
        reasons.append("long-range track uncertainty")

    if sensor_activation.radar and fusion_state in {"ACTIVE_TRACK", "FIRE", "KILL_ASSESS"}:
        confidence += 6
        reasons.append("radar-quality fire control")
    elif sensor_activation.irst and fusion_state in {"PASSIVE_TRACK", "AMBUSH"}:
        confidence += 3
        reasons.append("passive IR track correlation")

    if track_type in {"DRONE", "CRUISE_MISSILE"}:
        confidence -= 6
        reasons.append("small or low-signature target")
    if track_type == "BALLISTIC_MISSILE":
        confidence += 4
        reasons.append("strong ballistic signature")
    if track_type == "CRUISE_MISSILE" and altitude_m < 700:
        confidence -= 5
        reasons.append("terrain-mask profile")

    return max(0, min(99, confidence)), reasons


def choose_preferred_effector(track: JsonDict, score: int) -> str:
    range_m = float(track.get("range_m", 99999.0))
    if track.get("type") == "BALLISTIC_MISSILE":
        return "SAM"
    if range_m <= 2000:
        return "CIWS"
    if score >= 70:
        return "SAM"
    if score >= 40:
        return "JAMMER"
    return "MONITOR"


def shot_doctrine_for_track(track: JsonDict, score: int, doctrine: ShotDoctrine) -> str:
    if score >= 85 or track.get("type") in {"MISSILE", "CRUISE_MISSILE", "BALLISTIC_MISSILE", "JET"}:
        return doctrine.missile_mode_high_priority
    return doctrine.missile_mode_standard


@dataclass
class ShieldEngine:
    sensor_activation: SensorActivation = field(default_factory=SensorActivation)
    capacity: EngagementCapacity = field(default_factory=EngagementCapacity)
    doctrine: ShotDoctrine = field(default_factory=ShotDoctrine)
    sam_batteries: list[SamBatteryState] = field(
        default_factory=lambda: [SamBatteryState.from_config(config) for config in load_sam_batteries()]
    )
    current_time_s: float = 0.0
    previous_states: dict[str, str] = field(default_factory=dict)
    track_timings: dict[str, TrackTiming] = field(default_factory=dict)
    engagement_records: dict[str, EngagementRecord] = field(default_factory=dict)
    ciws_inventory: int = 1550

    def evaluate_snapshot(self, snapshot: JsonDict, dt: float = 1.0) -> JsonDict:
        self.current_time_s += dt
        tick_start_s = self.current_time_s - dt
        base = initial_snapshot()
        tracks = snapshot.get("tracks", [])
        events: list[JsonDict] = []
        assessed_tracks: list[JsonDict] = []
        hostile_candidates: list[JsonDict] = []
        active_ids = {track["id"] for track in tracks}

        stale_ids = set(self.track_timings) - active_ids
        for stale_id in stale_ids:
            self.track_timings.pop(stale_id, None)
            self.previous_states.pop(stale_id, None)

        for track in tracks:
            record = self.engagement_records.setdefault(
                track["id"],
                EngagementRecord(
                    health=_initial_health(track.get("type", "UNKNOWN")),
                    max_health=_initial_health(track.get("type", "UNKNOWN")),
                ),
            )
            if track.get("iff") != "HOSTILE":
                record.lifecycle_state = "MONITOR"

            timing = self.track_timings.setdefault(track["id"], TrackTiming())
            current_state, sensor_events = self._evaluate_track_state(track, timing, tick_start_s)
            events.extend(sensor_events)

            previous_state = self.previous_states.get(track["id"], "SILENT")
            score, reasons = threat_score(track)
            confidence, confidence_reasons = track_confidence(track, current_state, self.sensor_activation)
            preferred_effector = choose_preferred_effector(track, score)
            doctrine_mode = shot_doctrine_for_track(track, score, self.doctrine)

            assessed = {
                "id": track["id"],
                "fusion_state": current_state,
                "threat_score": score,
                "threat_reasons": reasons,
                "track_confidence": confidence,
                "confidence_reasons": confidence_reasons,
                "preferred_effector": preferred_effector,
                "shot_doctrine": doctrine_mode,
                "target_health": record.health,
                "target_max_health": record.max_health,
                "target_status": record.lifecycle_state,
            }
            assessed_tracks.append(assessed)
            self.previous_states[track["id"]] = current_state

            if (
                track.get("iff") == "HOSTILE"
                and track.get("alive", True)
                and not _is_terminal_status(record.lifecycle_state)
                and not _is_withdrawn_status(record.lifecycle_state)
            ):
                hostile_candidates.append({**track, **assessed})

            if current_state != previous_state and STATE_RANK[current_state] >= STATE_RANK["TRIPWIRE"]:
                events.append(
                    make_event(
                        "warning" if STATE_RANK[current_state] >= STATE_RANK["ACTIVE_TRACK"] else "info",
                        "fusion",
                        f"{track['id']} transitioned {previous_state} -> {current_state}.",
                    )
                )

        assignments, assignment_events = self._assign_effectors(hostile_candidates)
        events.extend(assignment_events)

        merged_tracks = []
        active_hostiles: list[JsonDict] = []
        for track in tracks:
            record = self.engagement_records[track["id"]]
            assessed = next(item for item in assessed_tracks if item["id"] == track["id"])
            assignment = assignments.get(
                track["id"],
                {
                    "assigned_effector": "MONITOR",
                    "assigned_battery": None,
                    "engagement_state": "MONITOR" if track.get("iff") != "HOSTILE" else "TRACKED",
                    "shots_planned": 0,
                    "shot_doctrine": assessed["shot_doctrine"],
                },
            )
            lifecycle_events = self._advance_engagement(track, record, assignment)
            events.extend(lifecycle_events)

            enriched = {
                **assessed,
                "assigned_effector": record.assigned_effector,
                "assigned_battery": record.assigned_battery,
                "engagement_state": record.lifecycle_state,
                "shots_planned": record.shots_planned,
                "shot_doctrine": record.shot_doctrine,
                "target_health": record.health,
                "target_max_health": record.max_health,
                "target_status": record.lifecycle_state,
            }
            merged_tracks.append(enriched)

            if (
                track.get("iff") == "HOSTILE"
                and track.get("alive", True)
                and not _is_terminal_status(record.lifecycle_state)
                and not _is_withdrawn_status(record.lifecycle_state)
            ):
                active_hostiles.append({**track, **enriched})

        ranked_hostiles = sorted(active_hostiles, key=lambda item: item["threat_score"], reverse=True)
        primary = ranked_hostiles[0] if ranked_hostiles else None
        ciws_target = next(
            (
                track
                for track in ranked_hostiles
                if track.get("assigned_effector") == "CIWS"
                and track.get("engagement_state") == "ENGAGING"
            ),
            None,
        )

        summary = base["summary"]
        summary.update(
            {
                "mode": primary["fusion_state"] if primary else "SILENT",
                "effector": self._summary_effector_label(primary) if primary else "SAM",
                "radar_emitting": any(
                    track["fusion_state"] in {"ACTIVE_TRACK", "FIRE", "KILL_ASSESS"}
                    for track in ranked_hostiles
                ),
            }
        )
        summary["sensors"].update(
            {
                "acoustic": self._sensor_display(
                    "acoustic",
                    any(track["fusion_state"] != "SILENT" for track in ranked_hostiles),
                ),
                "irst": self._sensor_display(
                    "irst",
                    any(
                        track["fusion_state"]
                        in {"PASSIVE_TRACK", "AMBUSH", "ACTIVE_TRACK", "FIRE", "KILL_ASSESS"}
                        for track in ranked_hostiles
                    ),
                ),
                "radar": self._sensor_display("radar", summary["radar_emitting"]),
            }
        )
        summary["ammo"].update(
            {
                "sam": self.total_sam_inventory(),
                "ciws_rounds": self.ciws_inventory,
            }
        )
        summary["sam_batteries"] = [
            {
                "id": battery.id,
                "name": battery.name,
                "ammo_remaining": battery.ammo_remaining,
                "max_channels": battery.max_channels,
                "status": battery.status,
            }
            for battery in self.sam_batteries
        ]

        ciws = base["ciws"]
        ciws.update(
            {
                "state": "FIRING" if ciws_target else "STANDBY",
                "ammo_remaining": self.ciws_inventory,
                "heat": 0.72 if ciws_target else 0.12,
                "spin_up": 0.5 if ciws_target else 0.0,
                "cooldown_remaining": 0.0 if ciws_target else 1.5,
                "active_target_id": ciws_target["id"] if ciws_target else None,
            }
        )

        passive_tracking = base["passive_tracking"]
        passive_tracking.update(
            {
                "acoustic_state": summary["sensors"]["acoustic"],
                "irst_state": summary["sensors"]["irst"],
                "radar_state": summary["sensors"]["radar"],
                "radar_blink_seconds": 1.5
                if any(track["fusion_state"] == "FIRE" for track in ranked_hostiles)
                else 0.0,
                "active_sensors": self.sensor_activation.labels(),
            }
        )

        if primary:
            primary_effector_label = self._summary_effector_label(primary)
            events.append(
                make_event(
                    "critical" if primary["assigned_effector"] == "CIWS" else "warning",
                    "assignment",
                    f"{primary['id']} priority {primary['threat_score']} assigned to {primary_effector_label} under {primary['shot_doctrine']}.",
                )
            )
        else:
            events.append(make_event("info", "assignment", "No hostile tracks require engagement."))

        return {
            "summary": summary,
            "tracks": merged_tracks,
            "ciws": ciws,
            "passive_tracking": passive_tracking,
            "defense_config": {
                "active_sensors": self.sensor_activation.labels(),
                "missile_channels": self.capacity.missile_channels,
                "jammer_channels": self.capacity.jammer_channels,
                "ciws_channels": self.capacity.ciws_channels,
                "high_priority_doctrine": self.doctrine.missile_mode_high_priority,
                "standard_doctrine": self.doctrine.missile_mode_standard,
                "hold_fire_below_score": self.doctrine.hold_fire_below_score,
            },
            "events": events,
        }

    def _assign_effectors(self, hostile_tracks: list[JsonDict]) -> tuple[dict[str, JsonDict], list[JsonDict]]:
        events: list[JsonDict] = []
        assignments: dict[str, JsonDict] = {}
        jammer_channels = self.capacity.jammer_channels
        ciws_channels = self.capacity.ciws_channels
        battery_channels = {
            battery.id: min(battery.max_channels, self.capacity.missile_channels)
            for battery in self.sam_batteries
        }

        ranked = sorted(hostile_tracks, key=lambda item: item["threat_score"], reverse=True)
        for track in ranked:
            score = track["threat_score"]
            preferred = track["preferred_effector"]
            assigned = "MONITOR"
            assigned_battery = None
            shots_planned = 0

            if score < self.doctrine.hold_fire_below_score:
                assignments[track["id"]] = {
                    "assigned_effector": "MONITOR",
                    "assigned_battery": None,
                    "engagement_state": "TRACKED",
                    "shots_planned": 0,
                    "shot_doctrine": track["shot_doctrine"],
                }
                events.append(
                    make_event(
                        "info",
                        "doctrine",
                        f"{track['id']} held at monitor due to doctrine threshold.",
                    )
                )
                continue

            if preferred == "CIWS" and ciws_channels > 0 and self.ciws_inventory >= 125 and track["fusion_state"] == "FIRE":
                assigned = "CIWS"
                ciws_channels -= 1
                shots_planned = 1
            elif preferred == "SAM" and self.total_sam_inventory() > 0 and track["fusion_state"] in {"AMBUSH", "ACTIVE_TRACK", "FIRE"}:
                doctrine_mode = track["shot_doctrine"]
                requested_shots = 2 if doctrine_mode == "SHOT_LOOK_SHOT" else 1
                battery = self._choose_sam_battery(track, requested_shots, battery_channels)
                if battery is not None:
                    assigned = "SAM"
                    assigned_battery = battery.id
                    available_shots = min(
                        requested_shots,
                        battery_channels[battery.id],
                        battery.ammo_remaining,
                    )
                    shots_planned = max(1, available_shots)
                    battery_channels[battery.id] -= shots_planned
            elif preferred == "JAMMER" and jammer_channels > 0 and track["fusion_state"] in {"PASSIVE_TRACK", "AMBUSH", "ACTIVE_TRACK", "FIRE"}:
                assigned = "JAMMER"
                jammer_channels -= 1
                shots_planned = 1

            if assigned == "MONITOR" and preferred != "MONITOR":
                events.append(
                    make_event(
                        "warning",
                        "capacity",
                        f"{track['id']} could not be assigned {preferred}; capacity exhausted or track state not ready.",
                    )
                )

            assignments[track["id"]] = {
                "assigned_effector": assigned,
                "assigned_battery": assigned_battery,
                "engagement_state": self._engagement_state(track["fusion_state"], assigned, track),
                "shots_planned": shots_planned,
                "shot_doctrine": track["shot_doctrine"],
            }
        return assignments, events

    def _choose_sam_battery(
        self,
        track: JsonDict,
        requested_shots: int,
        battery_channels: dict[str, int],
    ) -> SamBatteryState | None:
        track_position = track.get("position", {"x": 0.0, "y": 0.0})
        candidates: list[tuple[float, int, str, SamBatteryState]] = []
        for battery in self.sam_batteries:
            if battery.status != "READY":
                continue
            if battery.ammo_remaining <= 0 or battery_channels.get(battery.id, 0) <= 0:
                continue
            distance = _distance_between(track_position, battery.position)
            if distance > battery.max_range_m:
                continue
            shots_possible = min(
                requested_shots,
                battery_channels[battery.id],
                battery.ammo_remaining,
            )
            if shots_possible <= 0:
                continue
            candidates.append((distance, -shots_possible, battery.id, battery))

        if not candidates:
            return None

        candidates.sort(key=lambda item: (item[0], item[1], item[2]))
        return candidates[0][3]

    def _advance_engagement(
        self,
        track: JsonDict,
        record: EngagementRecord,
        assignment: JsonDict,
    ) -> list[JsonDict]:
        events: list[JsonDict] = []

        if track.get("iff") != "HOSTILE" or not track.get("alive", True):
            record.lifecycle_state = "MONITOR"
            record.assigned_effector = "MONITOR"
            record.assigned_battery = None
            return events

        assigned_effector = assignment.get("assigned_effector", "MONITOR")
        assigned_battery = assignment.get("assigned_battery")
        desired_shots = int(assignment.get("shots_planned", 0))
        doctrine_mode = assignment.get("shot_doctrine", record.shot_doctrine)

        if _is_terminal_status(record.lifecycle_state):
            return events

        if (
            assigned_effector != "MONITOR"
            and record.lifecycle_state not in {"ASSIGNED", "ENGAGING", "HIT", "MISS", "KILL_ASSESS"}
        ):
            record.lifecycle_state = "ASSIGNED"
            record.assigned_effector = assigned_effector
            record.assigned_battery = assigned_battery
            record.shot_doctrine = doctrine_mode
            record.shots_planned = desired_shots
            record.phase_started_at = self.current_time_s
            record.attempt_count += 1
            if assigned_effector == "SAM" and assigned_battery:
                battery = self._battery_by_id(assigned_battery)
                if battery is not None:
                    battery.ammo_remaining = max(0, battery.ammo_remaining - max(1, desired_shots))
            launcher_label = assigned_battery if assigned_effector == "SAM" and assigned_battery else assigned_effector
            events.append(make_event("warning", "engagement", f"{track['id']} opening fire with {launcher_label}."))
            return events

        if assigned_effector == "MONITOR" and record.lifecycle_state in {"TRACKED", "REATTACK", "OBSERVED"}:
            record.assigned_effector = "MONITOR"
            record.assigned_battery = None
            record.shots_planned = 0
            return events

        elapsed = self.current_time_s - record.phase_started_at

        if record.assigned_effector == "CIWS":
            if record.lifecycle_state == "ASSIGNED" and elapsed >= 0.5:
                record.lifecycle_state = "ENGAGING"
                record.phase_started_at = self.current_time_s
                self.ciws_inventory = max(0, self.ciws_inventory - 125)
                events.append(make_event("critical", "engagement", f"{track['id']} rounds on target."))
            elif record.lifecycle_state == "ENGAGING" and elapsed >= 0.5:
                record.lifecycle_state = "HIT"
                record.phase_started_at = self.current_time_s
                record.health = 0
                events.append(make_event("critical", "engagement", f"{track['id']} target hit by CIWS."))
            elif record.lifecycle_state == "HIT" and elapsed >= 0.4:
                record.lifecycle_state = "KILL_ASSESS"
                record.phase_started_at = self.current_time_s
            elif record.lifecycle_state == "KILL_ASSESS" and elapsed >= 0.5:
                record.lifecycle_state = "DESTROYED"
                record.assigned_effector = "MONITOR"
                record.assigned_battery = None
                events.append(make_event("critical", "engagement", f"{track['id']} destroyed by CIWS."))

        elif record.assigned_effector == "SAM":
            if record.lifecycle_state == "ASSIGNED" and elapsed >= 0.5:
                record.lifecycle_state = "ENGAGING"
                record.phase_started_at = self.current_time_s
                launcher_label = record.assigned_battery or "SAM"
                events.append(make_event("warning", "engagement", f"{track['id']} missile launched from {launcher_label}."))
            elif record.lifecycle_state == "ENGAGING" and elapsed >= 2.0:
                hit = _deterministic_hit(track, max(1, record.shots_planned))
                record.phase_started_at = self.current_time_s
                if hit:
                    record.lifecycle_state = "HIT"
                    damage = 100 if record.shots_planned >= 2 else 65
                    record.health = max(0, record.health - damage)
                    events.append(make_event("warning", "engagement", f"{track['id']} target hit by missile intercept."))
                else:
                    record.lifecycle_state = "MISS"
                    events.append(make_event("warning", "engagement", f"{track['id']} target missed by missile intercept."))
            elif record.lifecycle_state in {"HIT", "MISS"} and elapsed >= 0.75:
                record.lifecycle_state = "KILL_ASSESS"
                record.phase_started_at = self.current_time_s
            elif record.lifecycle_state == "KILL_ASSESS" and elapsed >= 0.75:
                track_type = str(track.get("type", "UNKNOWN"))
                if record.health <= 0:
                    record.lifecycle_state = "DESTROYED"
                    record.assigned_effector = "MONITOR"
                    record.assigned_battery = None
                    events.append(make_event("critical", "engagement", f"{track['id']} destroyed by missile intercept."))
                elif track_type in {"MISSILE", "CRUISE_MISSILE", "BALLISTIC_MISSILE"}:
                    record.lifecycle_state = "REATTACK"
                    record.assigned_effector = "MONITOR"
                    record.assigned_battery = None
                    record.shots_planned = 0
                    events.append(make_event("warning", "engagement", f"{track['id']} missile survived intercept; reattack required."))
                elif _abort_threshold(track_type) and record.health <= _abort_threshold(track_type):
                    record.lifecycle_state = "ABORTING"
                    record.assigned_effector = "MONITOR"
                    record.assigned_battery = None
                    record.shots_planned = 0
                    events.append(make_event("warning", "engagement", f"{track['id']} damaged and likely aborting attack."))
                else:
                    record.lifecycle_state = "DAMAGED"
                    record.assigned_effector = "MONITOR"
                    record.assigned_battery = None
                    record.shots_planned = 0
                    events.append(make_event("warning", "engagement", f"{track['id']} damaged but still mission-capable; reattack required."))

        elif record.assigned_effector == "JAMMER":
            if record.lifecycle_state == "ASSIGNED" and elapsed >= 1.0:
                record.lifecycle_state = "ENGAGING"
                record.phase_started_at = self.current_time_s
                events.append(make_event("info", "engagement", f"{track['id']} jamming active on target."))

        return events

    def _evaluate_track_state(
        self, track: JsonDict, timing: TrackTiming, tick_start_s: float
    ) -> tuple[str, list[JsonDict]]:
        events: list[JsonDict] = []
        if track.get("iff") != "HOSTILE" or not track.get("alive", True):
            return "SILENT", events

        range_m = float(track.get("range_m", 99999.0))
        altitude_m = float(track.get("altitude_m", 2500.0))
        acoustic_ready = False
        irst_ready = False
        radar_track_ready = False
        radar_fire_ready = False
        acoustic_just_detected = False
        irst_just_detected = False
        radar_just_tracked = False

        if self.sensor_activation.acoustic:
            acoustic_range_limit = 9000.0
            if track.get("type") == "CRUISE_MISSILE" and altitude_m < 700:
                acoustic_range_limit = 6200.0
            if track.get("type") == "BALLISTIC_MISSILE":
                acoustic_range_limit = 3000.0
            if range_m <= acoustic_range_limit:
                if timing.acoustic_entered_at is None:
                    timing.acoustic_entered_at = tick_start_s
                acoustic_delay = (range_m / SPEED_OF_SOUND_MPS) + 0.5
                if track.get("type") == "CRUISE_MISSILE":
                    acoustic_delay += 0.6
                elif track.get("type") == "BALLISTIC_MISSILE":
                    acoustic_delay += 0.2
                if self.current_time_s - timing.acoustic_entered_at >= acoustic_delay:
                    if timing.acoustic_detected_at is None:
                        timing.acoustic_detected_at = self.current_time_s
                        acoustic_just_detected = True
                        events.append(
                            make_event(
                                "info",
                                "sensor",
                                f"{track['id']} acoustic tripwire established after {acoustic_delay:.1f}s delay.",
                            )
                        )
                    acoustic_ready = True
            else:
                timing.acoustic_entered_at = None

        if self.sensor_activation.irst:
            heat_factor = _heat_factor(track)
            irst_range_limit = 7000.0 * heat_factor + 1200.0
            if track.get("type") == "CRUISE_MISSILE" and altitude_m < 700:
                irst_range_limit *= 0.8
            if track.get("type") == "BALLISTIC_MISSILE":
                irst_range_limit *= 1.1
            if range_m <= irst_range_limit:
                if timing.irst_entered_at is None:
                    timing.irst_entered_at = tick_start_s
                prereq_met = ((acoustic_ready and not acoustic_just_detected) or not self.sensor_activation.acoustic)
                irst_delay = 1.0 if prereq_met else 2.0
                if prereq_met and self.current_time_s - timing.irst_entered_at >= irst_delay:
                    if timing.irst_detected_at is None:
                        timing.irst_detected_at = self.current_time_s
                        irst_just_detected = True
                        events.append(make_event("info", "sensor", f"{track['id']} IRST passive track established."))
                    irst_ready = True
            else:
                timing.irst_entered_at = None

        if self.sensor_activation.radar:
            radar_range_limit = 4200.0
            if track.get("type") == "CRUISE_MISSILE" and altitude_m < 700:
                radar_range_limit = 2800.0
            elif track.get("type") == "BALLISTIC_MISSILE":
                radar_range_limit = 6500.0
            if range_m <= radar_range_limit:
                if timing.radar_entered_at is None:
                    timing.radar_entered_at = tick_start_s
                prereq_met = ((irst_ready and not irst_just_detected) or not self.sensor_activation.irst)
                track_delay = 0.5 if prereq_met else 1.0
                if prereq_met and self.current_time_s - timing.radar_entered_at >= track_delay:
                    if timing.radar_track_at is None:
                        timing.radar_track_at = self.current_time_s
                        radar_just_tracked = True
                        events.append(make_event("warning", "sensor", f"{track['id']} radar handoff established for precise tracking."))
                    radar_track_ready = True
                    if (
                        range_m <= 2000
                        and not radar_just_tracked
                        and self.current_time_s - timing.radar_track_at >= 1.5
                    ):
                        if timing.radar_fire_solution_at is None:
                            timing.radar_fire_solution_at = self.current_time_s
                            events.append(make_event("warning", "sensor", f"{track['id']} radar blink completed 1.5s fire-solution window."))
                        radar_fire_ready = True
            else:
                timing.radar_entered_at = None
                timing.radar_track_at = None
                timing.radar_fire_solution_at = None

        if radar_fire_ready:
            return "FIRE", events
        if radar_track_ready:
            return "ACTIVE_TRACK", events
        if irst_ready and range_m <= 4200:
            return "AMBUSH", events
        if irst_ready:
            return "PASSIVE_TRACK", events
        if acoustic_ready or (
            not self.sensor_activation.acoustic and self.sensor_activation.irst and timing.irst_detected_at is not None
        ):
            return "TRIPWIRE", events
        if not any((self.sensor_activation.acoustic, self.sensor_activation.irst, self.sensor_activation.radar)):
            return "SILENT", events
        if self.sensor_activation.radar and not (self.sensor_activation.acoustic or self.sensor_activation.irst):
            if radar_track_ready:
                return "ACTIVE_TRACK", events
            return ("TRIPWIRE" if range_m <= 4200 else "SILENT"), events
        return "SILENT", events

    def total_sam_inventory(self) -> int:
        return sum(max(0, battery.ammo_remaining) for battery in self.sam_batteries)

    def _battery_by_id(self, battery_id: str) -> SamBatteryState | None:
        return next((battery for battery in self.sam_batteries if battery.id == battery_id), None)

    def _summary_effector_label(self, track: JsonDict) -> str:
        effector = track.get("assigned_effector", "MONITOR")
        if effector == "SAM" and track.get("assigned_battery"):
            return f"SAM {track['assigned_battery']}"
        return effector

    def _sensor_display(self, sensor_name: str, active: bool) -> str:
        enabled = getattr(self.sensor_activation, sensor_name)
        if not enabled:
            return "DISABLED"
        if sensor_name == "acoustic":
            return "CONTACTS" if active else "LISTENING"
        if sensor_name == "irst":
            return "TRACKING" if active else "SCANNING"
        return "EMITTING" if active else "SILENT"

    def _engagement_state(self, fusion_state: str, effector: str, track: JsonDict) -> str:
        if track.get("iff") != "HOSTILE" or not track.get("alive", True):
            return "MONITOR"
        if effector == "MONITOR":
            return "TRACKED" if fusion_state != "SILENT" else "OBSERVED"
        if effector == "JAMMER":
            return "ASSIGNED"
        if effector == "SAM":
            return "ASSIGNED" if fusion_state in {"AMBUSH", "ACTIVE_TRACK"} else "ENGAGING"
        if effector == "CIWS":
            return "ENGAGING" if fusion_state == "FIRE" else "ASSIGNED"
        return "OBSERVED"
