from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
import re
from typing import Any, Literal

from scenarios import DEFAULT_SCENARIO_NAME, get_scenario, scenario_names
from shared.sam_config import load_sam_batteries
from shared.zone_config import load_defended_zones

JsonDict = dict[str, Any]
RoleName = Literal["hub", "pilot", "shield"]
MessageType = Literal["snapshot", "hub_registered", "role_update"]
PayloadType = Literal["registration", "snapshot", "role_update"]

SCHEMA_VERSION = "0.2.0"

TERMINAL_HOSTILE_STATUSES = {"DESTROYED", "NEUTRALIZED", "RETREAT"}
WITHDRAWN_HOSTILE_STATUSES = {"ABORTING", "RETREAT"}


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class EventRecord:
    timestamp: str
    level: str
    category: str
    message: str


@dataclass
class BattleLogRecord:
    id: int
    timestamp: str
    time_s: int
    source: str
    level: str
    category: str
    target_id: str | None
    message: str


def make_event(level: str, category: str, message: str) -> JsonDict:
    return asdict(
        EventRecord(
            timestamp=utc_now_iso(),
            level=level,
            category=category,
            message=message,
        )
    )


def make_battle_log_entry(
    *,
    entry_id: int,
    time_s: int,
    source: str,
    level: str,
    category: str,
    target_id: str | None,
    message: str,
    timestamp: str | None = None,
) -> JsonDict:
    return asdict(
        BattleLogRecord(
            id=entry_id,
            timestamp=timestamp or utc_now_iso(),
            time_s=time_s,
            source=source,
            level=level,
            category=category,
            target_id=target_id,
            message=message,
        )
    )


TRACK_ID_PATTERN = re.compile(r"\b[A-Z]+-\d+\b")
ZONE_IMPACT_PATTERN = re.compile(r"^(?P<zone>.+?) impacted by (?P<track>[A-Z]+-\d+) for (?P<damage>\d+)% damage\.$")


def initial_snapshot() -> JsonDict:
    default_scenario = get_scenario(DEFAULT_SCENARIO_NAME)
    sam_batteries = load_sam_batteries()
    return {
        "summary": {
            "mode": "PASSIVE_TRACK",
            "track_count": 0,
            "ammo": {
                "sam": sum(int(battery.get("ammo", 0)) for battery in sam_batteries),
                "ciws_rounds": 1550,
            },
            "sensors": {
                "acoustic": "LISTENING",
                "irst": "SCANNING",
                "radar": "SILENT",
            },
            "effector": "SAM",
            "radar_emitting": False,
        },
        "tracks": [],
        "defended_zones": load_defended_zones(),
        "sam_batteries": sam_batteries,
        "defense_config": {},
        "events": [],
        "battle_log": [],
        "ciws": {
            "state": "STANDBY",
            "ammo_remaining": 1550,
            "heat": 0.08,
            "spin_up": 0.0,
            "cooldown_remaining": 0.0,
            "active_target_id": None,
        },
        "passive_tracking": {
            "acoustic_state": "LISTENING",
            "irst_state": "SCANNING",
            "radar_state": "SILENT",
            "radar_blink_seconds": 0.0,
        },
        "scenario": {
            "name": default_scenario.name,
            "status": "RUNNING",
            "execution_state": "RUNNING",
            "doctrine_mode": "BALANCED",
            "reason": "",
            "elapsed_s": 0,
            "time_limit_s": default_scenario.time_limit_s,
            "revision": 0,
            "step_budget": 0,
            "available_scenarios": scenario_names(),
            "available_doctrine_modes": ["AGGRESSIVE", "BALANCED", "CONSERVATIVE"],
        },
        "report": {},
        "meta": {
            "schema_version": SCHEMA_VERSION,
            "last_role": "hub",
            "updated_at": utc_now_iso(),
        },
    }


@dataclass
class MessageEnvelope:
    schema_version: str
    type: MessageType
    source: RoleName
    timestamp: str
    payload_type: PayloadType
    payload: JsonDict

    def to_dict(self) -> JsonDict:
        return asdict(self)


def envelope(
    message_type: MessageType,
    source: RoleName,
    payload_type: PayloadType,
    payload: JsonDict,
) -> JsonDict:
    return MessageEnvelope(
        schema_version=SCHEMA_VERSION,
        type=message_type,
        source=source,
        timestamp=utc_now_iso(),
        payload_type=payload_type,
        payload=payload,
    ).to_dict()


def make_registration_payload(role: RoleName, snapshot: JsonDict) -> JsonDict:
    return {"role": role, "snapshot": snapshot}


def make_snapshot_payload(snapshot: JsonDict) -> JsonDict:
    snapshot_copy = deepcopy(snapshot)
    snapshot_copy.setdefault("meta", {})
    snapshot_copy["meta"].update(
        {
            "schema_version": SCHEMA_VERSION,
            "payload_type": "snapshot",
        }
    )
    return snapshot_copy


def make_role_update_payload(
    *,
    tracks: list[JsonDict] | None = None,
    summary: JsonDict | None = None,
    ciws: JsonDict | None = None,
    passive_tracking: JsonDict | None = None,
    defense_config: JsonDict | None = None,
    scenario: JsonDict | None = None,
    report: JsonDict | None = None,
    events: list[JsonDict] | None = None,
) -> JsonDict:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "payload_type": "role_update",
        "tracks": tracks or [],
        "summary": summary or {},
        "ciws": ciws or {},
        "passive_tracking": passive_tracking or {},
        "defense_config": defense_config or {},
        "scenario": scenario or {},
        "report": report or {},
        "events": events or [],
    }
    return payload


def registration_message(role: RoleName, snapshot: JsonDict) -> JsonDict:
    return envelope(
        "hub_registered",
        "hub",
        "registration",
        make_registration_payload(role, make_snapshot_payload(snapshot)),
    )


def snapshot_message(snapshot: JsonDict) -> JsonDict:
    return envelope("snapshot", "hub", "snapshot", make_snapshot_payload(snapshot))


def role_update_message(role: RoleName, payload: JsonDict) -> JsonDict:
    normalized = make_role_update_payload(
        tracks=payload.get("tracks"),
        summary=payload.get("summary"),
        ciws=payload.get("ciws"),
        passive_tracking=payload.get("passive_tracking"),
        defense_config=payload.get("defense_config"),
        scenario=payload.get("scenario"),
        report=payload.get("report"),
        events=payload.get("events"),
    )
    return envelope("role_update", role, "role_update", normalized)


def normalize_role_update_payload(payload: JsonDict) -> JsonDict:
    return make_role_update_payload(
        tracks=payload.get("tracks"),
        summary=payload.get("summary"),
        ciws=payload.get("ciws"),
        passive_tracking=payload.get("passive_tracking"),
        defense_config=payload.get("defense_config"),
        scenario=payload.get("scenario"),
        report=payload.get("report"),
        events=payload.get("events"),
    )


@dataclass
class HubState:
    snapshot: JsonDict = field(default_factory=initial_snapshot)
    known_hostiles: set[str] = field(default_factory=set)
    hostile_history: dict[str, JsonDict] = field(default_factory=dict)
    zone_impacts: dict[str, int] = field(default_factory=dict)
    initial_sam_inventory: int = 0
    initial_ciws_inventory: int = 1550
    battle_log_counter: int = 0
    battle_log_signatures: set[tuple[int, str, str, str, str | None]] = field(default_factory=set)

    @classmethod
    def create(cls) -> "HubState":
        snapshot = initial_snapshot()
        return cls(
            snapshot=snapshot,
            initial_sam_inventory=int(snapshot["summary"]["ammo"].get("sam", 0)),
            initial_ciws_inventory=int(snapshot["summary"]["ammo"].get("ciws_rounds", 1550)),
        )

    def merge_role_update(self, role: str, payload: JsonDict) -> JsonDict:
        normalized = normalize_role_update_payload(payload)
        snapshot = self.snapshot

        if role == "pilot" or normalized["tracks"]:
            existing = {track["id"]: track for track in snapshot["tracks"]}
            if role == "pilot":
                incoming_ids = {track["id"] for track in normalized["tracks"] if "id" in track}
                existing = {
                    track_id: track
                    for track_id, track in existing.items()
                    if track_id in incoming_ids
                }
            for track in normalized["tracks"]:
                merged = deepcopy(existing.get(track["id"], {}))
                merged.update(track)
                existing[track["id"]] = merged
            snapshot["tracks"] = sorted(
                [track for track in existing.values() if track.get("alive", True)],
                key=lambda track: track["id"],
            )
            snapshot["summary"]["track_count"] = len(snapshot["tracks"])

        if normalized["summary"]:
            summary = snapshot["summary"]
            summary.update(normalized["summary"])
            if "ammo" in normalized["summary"]:
                summary["ammo"].update(normalized["summary"]["ammo"])
            if "sensors" in normalized["summary"]:
                summary["sensors"].update(normalized["summary"]["sensors"])

        if normalized["ciws"]:
            snapshot["ciws"].update(normalized["ciws"])

        if normalized["passive_tracking"]:
            snapshot["passive_tracking"].update(normalized["passive_tracking"])

        if normalized["defense_config"]:
            snapshot["defense_config"].update(normalized["defense_config"])

        if normalized["scenario"]:
            snapshot["scenario"].update(normalized["scenario"])

        if normalized["report"]:
            snapshot["report"].update(normalized["report"])

        if normalized["events"]:
            snapshot["events"] = (normalized["events"] + snapshot["events"])[:40]
            self._append_battle_log_events(role, normalized["events"], normalized["scenario"])

        for track in snapshot["tracks"]:
            if track.get("iff") == "HOSTILE":
                self.known_hostiles.add(track["id"])
                history_record = deepcopy(self.hostile_history.get(track["id"], {}))
                history_record.update(track)
                self.hostile_history[track["id"]] = history_record

        snapshot["meta"] = {
            "last_role": role,
            "updated_at": utc_now_iso(),
            "schema_version": SCHEMA_VERSION,
            "payload_type": "snapshot",
        }
        return snapshot

    def evaluate_scenario(self) -> JsonDict:
        snapshot = self.snapshot
        scenario = snapshot["scenario"]
        if scenario.get("status") != "RUNNING":
            return snapshot

        elapsed_s = int(scenario.get("elapsed_s", 0))
        time_limit_s = int(scenario.get("time_limit_s", get_scenario(scenario.get("name")).time_limit_s))
        tracks = snapshot.get("tracks", [])
        zones = snapshot.get("defended_zones", [])
        zone_events = self._apply_zone_impacts(tracks, zones, elapsed_s)
        if zone_events:
            snapshot["events"] = (zone_events + snapshot["events"])[:40]
            self._append_battle_log_events("hub", zone_events)
        active_hostiles = [
            track
            for track in tracks
            if track.get("iff") == "HOSTILE"
            and track.get("alive", True)
            and track.get("target_status") not in TERMINAL_HOSTILE_STATUSES
            and track.get("target_status") not in WITHDRAWN_HOSTILE_STATUSES
            and not track.get("retreating", False)
        ]
        destroyed = [
            track for track in tracks if track.get("iff") == "HOSTILE" and track.get("target_status") == "DESTROYED"
        ]
        neutralized = [
            track for track in tracks if track.get("iff") == "HOSTILE" and track.get("target_status") == "NEUTRALIZED"
        ]
        retreating = [
            track
            for track in tracks
            if track.get("iff") == "HOSTILE"
            and (
                track.get("target_status") in WITHDRAWN_HOSTILE_STATUSES
                or track.get("retreating")
            )
        ]

        outcome = None
        reason = ""
        penetrators = [zone for zone in zones if int(zone.get("health", 100)) <= 0]
        if penetrators:
            outcome = "FAILURE"
            reason = "A defended asset zone was critically damaged."
        elif elapsed_s >= time_limit_s:
            outcome = "TIMEOUT"
            reason = "Scenario time limit reached."
        elif not active_hostiles and (destroyed or neutralized or retreating or self.known_hostiles):
            outcome = "SUCCESS"
            reason = "All hostile tracks neutralized or forced to retreat."
        elif (
            active_hostiles
            and int(snapshot["summary"]["ammo"].get("sam", 0)) <= 0
            and int(snapshot["summary"]["ammo"].get("ciws_rounds", 0)) < 125
        ):
            outcome = "FAILURE"
            reason = "Defensive ammunition exhausted against remaining hostile tracks."

        if outcome is None:
            return snapshot

        scenario.update({"status": outcome, "reason": reason})
        snapshot["report"] = self.generate_report(outcome, reason)
        self._append_battle_log_events("hub", [make_event("info", "scenario", f"Scenario concluded with {outcome}: {reason}")])
        return snapshot

    def stop_scenario(self, reason: str = "Operator stop requested.") -> JsonDict:
        scenario = self.snapshot["scenario"]
        if scenario.get("status") == "RUNNING":
            scenario.update({"status": "STOPPED", "execution_state": "STOPPED", "step_budget": 0, "reason": reason})
            self.snapshot["report"] = self.generate_report("STOPPED", reason)
            event = make_event("warning", "scenario", reason)
            self.snapshot["events"] = ([event] + self.snapshot["events"])[:40]
            self._append_battle_log_events("hub", [event])
            self.snapshot["meta"] = {
                "last_role": "hub",
                "updated_at": utc_now_iso(),
                "schema_version": SCHEMA_VERSION,
                "payload_type": "snapshot",
            }
        return self.snapshot

    def reset_scenario(self, scenario_name: str | None = None) -> JsonDict:
        previous = self.snapshot
        chosen = get_scenario(scenario_name or previous["scenario"].get("name"))
        current_revision = int(previous.get("scenario", {}).get("revision", 0))
        self.snapshot = initial_snapshot()
        self.snapshot["scenario"].update(
            {
                "name": chosen.name,
                "status": "RUNNING",
                "execution_state": "RUNNING",
                "doctrine_mode": previous["scenario"].get("doctrine_mode", "BALANCED"),
                "reason": "",
                "elapsed_s": 0,
                "time_limit_s": chosen.time_limit_s,
                "revision": current_revision + 1,
                "step_budget": 0,
                "available_scenarios": scenario_names(),
                "available_doctrine_modes": ["AGGRESSIVE", "BALANCED", "CONSERVATIVE"],
            }
        )
        reset_event = make_event("info", "scenario", f"Scenario reset to {chosen.name}.")
        self.snapshot["events"] = [reset_event]
        self.snapshot["battle_log"] = []
        self.known_hostiles = set()
        self.hostile_history = {}
        self.zone_impacts = {}
        self.initial_sam_inventory = int(self.snapshot["summary"]["ammo"].get("sam", 0))
        self.initial_ciws_inventory = int(self.snapshot["summary"]["ammo"].get("ciws_rounds", 1550))
        self.battle_log_counter = 0
        self.battle_log_signatures = set()
        self._append_battle_log_events("hub", [reset_event])
        self.snapshot["meta"] = {
            "last_role": "hub",
            "updated_at": utc_now_iso(),
            "schema_version": SCHEMA_VERSION,
            "payload_type": "snapshot",
        }
        return self.snapshot

    def pause_scenario(self) -> JsonDict:
        scenario = self.snapshot["scenario"]
        if scenario.get("status") == "RUNNING":
            scenario.update({"execution_state": "PAUSED", "step_budget": 0})
            event = make_event("info", "scenario", "Simulation paused.")
            self.snapshot["events"] = ([event] + self.snapshot["events"])[:40]
            self._append_battle_log_events("hub", [event])
        return self.snapshot

    def resume_scenario(self) -> JsonDict:
        scenario = self.snapshot["scenario"]
        if scenario.get("status") == "RUNNING":
            scenario.update({"execution_state": "RUNNING", "step_budget": 0})
            event = make_event("info", "scenario", "Simulation resumed.")
            self.snapshot["events"] = ([event] + self.snapshot["events"])[:40]
            self._append_battle_log_events("hub", [event])
        return self.snapshot

    def step_scenario(self) -> JsonDict:
        scenario = self.snapshot["scenario"]
        if scenario.get("status") == "RUNNING" and scenario.get("execution_state") == "PAUSED":
            scenario["step_budget"] = int(scenario.get("step_budget", 0)) + 1
            event = make_event("info", "scenario", "Simulation stepped by one tick.")
            self.snapshot["events"] = ([event] + self.snapshot["events"])[:40]
            self._append_battle_log_events("hub", [event])
        return self.snapshot

    def set_doctrine_mode(self, doctrine_mode: str) -> JsonDict:
        normalized = doctrine_mode.strip().upper()
        allowed = {"AGGRESSIVE", "BALANCED", "CONSERVATIVE"}
        if normalized not in allowed:
            normalized = "BALANCED"
        self.snapshot["scenario"]["doctrine_mode"] = normalized
        event = make_event("info", "doctrine", f"Doctrine set to {normalized}.")
        self.snapshot["events"] = ([event] + self.snapshot["events"])[:40]
        self._append_battle_log_events("hub", [event])
        return self.snapshot

    def export_battle_log(self) -> JsonDict:
        return {
            "scenario": {
                "name": self.snapshot["scenario"].get("name", "-"),
                "status": self.snapshot["scenario"].get("status", "RUNNING"),
                "elapsed_s": int(self.snapshot["scenario"].get("elapsed_s", 0)),
                "time_limit_s": int(self.snapshot["scenario"].get("time_limit_s", 0)),
                "doctrine_mode": self.snapshot["scenario"].get("doctrine_mode", "BALANCED"),
            },
            "battle_log": deepcopy(self.snapshot.get("battle_log", [])),
        }

    def generate_report(self, outcome: str, reason: str) -> JsonDict:
        hostile_tracks = list(self.hostile_history.values())
        zones = self.snapshot.get("defended_zones", [])
        destroyed = [track for track in hostile_tracks if track.get("target_status") == "DESTROYED"]
        neutralized = [track for track in hostile_tracks if track.get("target_status") == "NEUTRALIZED"]
        retreating = [
            track
            for track in hostile_tracks
            if track.get("target_status") in WITHDRAWN_HOSTILE_STATUSES or track.get("retreating")
        ]
        active = [
            track
            for track in hostile_tracks
            if track.get("target_status") not in TERMINAL_HOSTILE_STATUSES
            and track.get("target_status") not in WITHDRAWN_HOSTILE_STATUSES
            and not track.get("retreating", False)
        ]
        sam_remaining = int(self.snapshot["summary"]["ammo"].get("sam", 0))
        ciws_remaining = int(self.snapshot["summary"]["ammo"].get("ciws_rounds", 0))
        sam_expended = self.initial_sam_inventory - sam_remaining
        ciws_expended = self.initial_ciws_inventory - ciws_remaining

        outcome_label = {
            "SUCCESS": "Defense Successful",
            "FAILURE": "Defense Failed",
            "TIMEOUT": "Scenario Timed Out",
            "STOPPED": "Simulation Stopped",
        }.get(outcome, outcome)

        hostile_history = [
            {
                "id": track.get("id", "UNKNOWN"),
                "type": track.get("type", "UNKNOWN"),
                "final_status": track.get("target_status", "UNKNOWN"),
                "engagement_state": track.get("engagement_state", "-"),
                "target_health": int(track.get("target_health", 0)),
                "target_max_health": int(track.get("target_max_health", track.get("target_health", 0))),
                "retreating": bool(track.get("retreating", False)),
            }
            for track in sorted(hostile_tracks, key=lambda item: item.get("id", ""))
        ]

        return {
            "title": "Post-Simulation Assessment",
            "outcome": outcome,
            "outcome_label": outcome_label,
            "executive_summary": reason,
            "metrics": {
                "hostiles_tracked": len(self.known_hostiles),
                "hostiles_active": len(active),
                "hostiles_destroyed": len(destroyed),
                "hostiles_neutralized": len(neutralized),
                "hostiles_retreated": len(retreating),
                "zones_secure": len([zone for zone in zones if int(zone.get("health", 100)) >= 75]),
                "zones_damaged": len([zone for zone in zones if 0 < int(zone.get("health", 100)) < 75]),
                "zones_lost": len([zone for zone in zones if int(zone.get("health", 100)) <= 0]),
                "sam_expended": max(0, sam_expended),
                "ciws_rounds_expended": max(0, ciws_expended),
            },
            "findings": [
                f"Tracked {len(self.known_hostiles)} hostile contacts during the scenario.",
                f"Destroyed {len(destroyed)} hostile contacts, neutralized {len(neutralized)}, and forced {len(retreating)} to retreat.",
                f"Expended {max(0, sam_expended)} SAM shots and {max(0, ciws_expended)} CIWS rounds.",
            ],
            "recommendations": [
                "Review engagement timelines for capacity bottlenecks.",
                "Compare doctrine settings against surviving or retreating hostile tracks.",
                "Inspect sensor handoff delays for missed or late engagements.",
            ],
            "hostile_history": hostile_history,
        }

    def _apply_zone_impacts(
        self,
        tracks: list[JsonDict],
        zones: list[JsonDict],
        elapsed_s: int,
    ) -> list[JsonDict]:
        events: list[JsonDict] = []
        for track in tracks:
            if track.get("iff") != "HOSTILE" or not track.get("alive", True):
                continue
            if track.get("target_status") in TERMINAL_HOSTILE_STATUSES or track.get("target_status") in WITHDRAWN_HOSTILE_STATUSES:
                continue
            track_position = track.get("position", {})
            track_x = float(track_position.get("x", 0.0))
            track_y = float(track_position.get("y", 0.0))
            for zone in zones:
                zone_position = zone.get("position", {})
                dx = track_x - float(zone_position.get("x", 0.0))
                dy = track_y - float(zone_position.get("y", 0.0))
                if (dx * dx + dy * dy) ** 0.5 > float(zone.get("radius_m", 0.0)):
                    continue
                impact_key = f"{track.get('id')}:{zone.get('id')}"
                last_impact_s = self.zone_impacts.get(impact_key)
                if last_impact_s is not None and elapsed_s - last_impact_s < 3:
                    continue
                self.zone_impacts[impact_key] = elapsed_s
                damage = {
                    "BALLISTIC_MISSILE": 85,
                    "CRUISE_MISSILE": 55,
                    "MISSILE": 70,
                    "JET": 45,
                    "HELICOPTER": 35,
                    "DRONE": 20,
                }.get(track.get("type", "UNKNOWN"), 25)
                zone["health"] = max(0, int(zone.get("health", 100)) - damage)
                zone["status"] = "LOST" if zone["health"] <= 0 else ("DAMAGED" if zone["health"] < 100 else "SECURE")
                events.append(
                    make_event(
                        "critical" if zone["health"] <= 0 else "warning",
                        "zone",
                        f"{zone.get('name', zone.get('id'))} impacted by {track.get('id')} for {damage}% damage.",
                    )
                )
        return events

    def _append_battle_log_events(
        self,
        source: str,
        events: list[JsonDict],
        scenario_override: JsonDict | None = None,
    ) -> None:
        if not events:
            return
        time_s = int((scenario_override or {}).get("elapsed_s", self.snapshot.get("scenario", {}).get("elapsed_s", 0)))
        existing = self.snapshot.setdefault("battle_log", [])
        for event in events:
            curated = self._curate_battle_log_event(source, event, time_s)
            if curated is None:
                continue
            signature = (
                int(curated["time_s"]),
                str(curated["source"]),
                str(curated["category"]),
                str(curated["message"]),
                curated.get("target_id"),
            )
            if signature in self.battle_log_signatures:
                continue
            self.battle_log_signatures.add(signature)
            self.battle_log_counter += 1
            existing.append(
                make_battle_log_entry(
                    entry_id=self.battle_log_counter,
                    time_s=int(curated["time_s"]),
                    source=str(curated["source"]),
                    level=str(curated["level"]),
                    category=str(curated["category"]),
                    target_id=curated.get("target_id"),
                    message=str(curated["message"]),
                    timestamp=str(curated["timestamp"]),
                )
            )

    def _curate_battle_log_event(self, source: str, event: JsonDict, time_s: int) -> JsonDict | None:
        category = str(event.get("category", "system")).lower()
        level = str(event.get("level", "info"))
        message = str(event.get("message", "")).strip()
        timestamp = str(event.get("timestamp", utc_now_iso()))
        if not message:
            return None

        curated_category = category
        curated_message = message
        target_id = self._extract_target_id(message)

        if category == "sensor":
            if "tripwire alert" in message.lower():
                curated_category = "detection"
            elif any(token in message.lower() for token in ("passive track established", "radar handoff established", "radar blink completed")):
                curated_category = "handoff"
            else:
                return None
        elif category == "assignment":
            if "no hostile tracks require engagement" in message.lower() or "could not be assigned" in message.lower():
                return None
            curated_category = "assignment"
        elif category == "engagement":
            lowered = message.lower()
            if "rounds on target" in lowered:
                return None
            if any(token in lowered for token in ("opening fire", "missile launched", "jamming active")):
                curated_category = "weapon_release"
            elif "target hit" in lowered:
                curated_category = "hit"
            elif "target missed" in lowered:
                curated_category = "miss"
            elif any(token in lowered for token in ("destroyed", "aborting attack", "reattack required", "survived intercept")):
                curated_category = "outcome"
            else:
                return None
        elif category == "zone":
            match = ZONE_IMPACT_PATTERN.match(message)
            if not match:
                return None
            target_id = match.group("track")
            curated_category = "zone_impact"
            curated_message = f"{match.group('zone')} hit by {target_id}; zone damage {match.group('damage')}%."
        elif category == "scenario":
            lowered = message.lower()
            if any(token in lowered for token in ("paused", "resumed", "stepped")):
                return None
            curated_category = "scenario"
        elif category == "doctrine":
            return None
        else:
            return None

        return {
            "time_s": time_s,
            "source": source,
            "level": level,
            "category": curated_category.upper(),
            "target_id": target_id,
            "message": curated_message,
            "timestamp": timestamp,
        }

    def _extract_target_id(self, message: str) -> str | None:
        match = TRACK_ID_PATTERN.search(message)
        return match.group(0) if match else None
