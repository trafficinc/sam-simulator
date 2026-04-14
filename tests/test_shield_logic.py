import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from shield import config as shield_config
from shield.config import load_capacity, load_doctrine, load_sensor_activation
from shield.logic import (
    EngagementCapacity,
    SamBatteryState,
    SensorActivation,
    ShieldEngine,
    ShotDoctrine,
    choose_preferred_effector,
    doctrine_from_mode,
    shot_doctrine_for_track,
    threat_score,
)


class ShieldLogicTests(unittest.TestCase):
    def test_fusion_state_progression_by_range(self):
        acoustic_engine = ShieldEngine(sensor_activation=SensorActivation(acoustic=True, irst=False, radar=False))
        track = {
            "id": "T-100",
            "type": "JET",
            "iff": "HOSTILE",
            "alive": True,
            "range_m": 3000,
            "speed_mps": 180,
            "position": {"x": 3000, "y": 0},
            "heading_deg": 180,
        }
        self.assertEqual(acoustic_engine.evaluate_snapshot({"tracks": [track]}, dt=10.0)["summary"]["mode"], "TRIPWIRE")

        engine = ShieldEngine()
        staged_track = dict(track)
        self.assertEqual(engine.evaluate_snapshot({"tracks": [staged_track]}, dt=10.0)["summary"]["mode"], "TRIPWIRE")
        self.assertEqual(engine.evaluate_snapshot({"tracks": [staged_track]}, dt=2.0)["summary"]["mode"], "AMBUSH")
        self.assertEqual(engine.evaluate_snapshot({"tracks": [staged_track]}, dt=1.0)["summary"]["mode"], "ACTIVE_TRACK")

        fire_track = dict(staged_track)
        fire_track["range_m"] = 1500
        fire_track["position"] = {"x": 1500, "y": 0}
        self.assertEqual(engine.evaluate_snapshot({"tracks": [fire_track]}, dt=1.0)["summary"]["mode"], "ACTIVE_TRACK")
        self.assertEqual(engine.evaluate_snapshot({"tracks": [fire_track]}, dt=1.5)["summary"]["mode"], "FIRE")

    def test_threat_score_favors_fast_close_missile(self):
        missile = {
            "type": "CRUISE_MISSILE",
            "iff": "HOSTILE",
            "alive": True,
            "range_m": 1500,
            "altitude_m": 250,
            "speed_mps": 280,
            "position": {"x": 1500, "y": 0},
            "heading_deg": 180,
        }
        drone = {
            "type": "DRONE",
            "iff": "HOSTILE",
            "alive": True,
            "range_m": 5000,
            "speed_mps": 80,
            "position": {"x": 5000, "y": 0},
            "heading_deg": 0,
        }
        missile_score, missile_reasons = threat_score(missile)
        drone_score, _ = threat_score(drone)
        self.assertGreater(missile_score, drone_score)
        self.assertIn("inside close-in envelope", missile_reasons)

    def test_ballistic_missile_scores_above_cruise_missile(self):
        ballistic = {
            "type": "BALLISTIC_MISSILE",
            "iff": "HOSTILE",
            "alive": True,
            "range_m": 4200,
            "altitude_m": 14000,
            "speed_mps": 520,
            "position": {"x": 4200, "y": 0},
            "heading_deg": 180,
        }
        cruise = {
            "type": "CRUISE_MISSILE",
            "iff": "HOSTILE",
            "alive": True,
            "range_m": 6200,
            "altitude_m": 250,
            "speed_mps": 200,
            "position": {"x": 6200, "y": 0},
            "heading_deg": 180,
        }
        ballistic_score, ballistic_reasons = threat_score(ballistic)
        cruise_score, _ = threat_score(cruise)
        self.assertGreater(ballistic_score, cruise_score)
        self.assertIn("high altitude short-reaction profile", ballistic_reasons)

    def test_effector_selection_prefers_ciws_inside_envelope(self):
        close_track = {"range_m": 1200}
        distant_track = {"range_m": 4200}
        self.assertEqual(choose_preferred_effector(close_track, 90), "CIWS")
        self.assertEqual(choose_preferred_effector(distant_track, 90), "SAM")

    def test_engine_emits_transition_and_assignment_events(self):
        engine = ShieldEngine()
        track = {
            "id": "T-004",
            "type": "MISSILE",
            "iff": "HOSTILE",
            "alive": True,
            "range_m": 1500,
            "speed_mps": 280,
            "position": {"x": 1500, "y": 0},
            "heading_deg": 180,
        }
        engine.evaluate_snapshot({"tracks": [track]}, dt=6.0)
        engine.evaluate_snapshot({"tracks": [track]}, dt=2.0)
        engine.evaluate_snapshot({"tracks": [track]}, dt=1.0)
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=1.5)
        self.assertEqual(payload["summary"]["mode"], "FIRE")
        self.assertEqual(payload["summary"]["effector"], "CIWS")
        self.assertEqual(payload["tracks"][0]["assigned_effector"], "CIWS")
        self.assertEqual(payload["tracks"][0]["target_status"], "ASSIGNED")
        messages = [event["message"] for event in payload["events"]]
        self.assertTrue(any("radar blink completed" in message for message in messages))
        self.assertTrue(any("assigned to CIWS" in message for message in messages))
        self.assertIn("defense_config", payload)
        self.assertGreaterEqual(payload["tracks"][0]["track_confidence"], 0)

    def test_ciws_lifecycle_reaches_destroyed(self):
        engine = ShieldEngine()
        track = {
            "id": "T-700",
            "type": "MISSILE",
            "iff": "HOSTILE",
            "alive": True,
            "range_m": 1500,
            "speed_mps": 280,
            "position": {"x": 1500, "y": 0},
            "heading_deg": 180,
        }
        engine.evaluate_snapshot({"tracks": [track]}, dt=6.0)
        engine.evaluate_snapshot({"tracks": [track]}, dt=2.0)
        engine.evaluate_snapshot({"tracks": [track]}, dt=1.0)
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=1.5)
        self.assertEqual(payload["tracks"][0]["target_status"], "ASSIGNED")
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=0.5)
        self.assertEqual(payload["tracks"][0]["target_status"], "ENGAGING")
        self.assertEqual(payload["ciws"]["active_target_id"], "T-700")
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=0.5)
        self.assertEqual(payload["tracks"][0]["target_status"], "HIT")
        self.assertEqual(payload["tracks"][0]["target_health"], 0)
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=0.4)
        self.assertEqual(payload["tracks"][0]["target_status"], "KILL_ASSESS")
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=0.5)
        self.assertEqual(payload["tracks"][0]["target_status"], "DESTROYED")
        messages = [event["message"] for event in payload["events"]]
        self.assertTrue(any("destroyed by CIWS" in message for message in messages))

    def test_missile_lifecycle_can_require_reattack(self):
        engine = ShieldEngine(
            capacity=EngagementCapacity(missile_channels=1, jammer_channels=0, ciws_channels=0),
            sensor_activation=SensorActivation(acoustic=False, irst=False, radar=True),
            doctrine=ShotDoctrine(missile_mode_high_priority="SINGLE_SHOT", missile_mode_standard="SINGLE_SHOT"),
        )
        track = {
            "id": "T-402",
            "type": "MISSILE",
            "iff": "HOSTILE",
            "alive": True,
            "range_m": 3000,
            "speed_mps": 280,
            "position": {"x": 3000, "y": 0},
            "heading_deg": 180,
        }
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=2.0)
        self.assertEqual(payload["tracks"][0]["target_status"], "ASSIGNED")
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=0.5)
        self.assertEqual(payload["tracks"][0]["target_status"], "ENGAGING")
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=2.0)
        self.assertEqual(payload["tracks"][0]["target_status"], "MISS")
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=0.75)
        self.assertEqual(payload["tracks"][0]["target_status"], "KILL_ASSESS")
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=0.75)
        self.assertEqual(payload["tracks"][0]["target_status"], "REATTACK")
        messages = [event["message"] for event in payload["events"]]
        self.assertTrue(any("reattack required" in message for message in messages))

    def test_aircraft_hit_can_transition_to_aborting(self):
        engine = ShieldEngine(
            capacity=EngagementCapacity(missile_channels=1, jammer_channels=0, ciws_channels=0),
            sensor_activation=SensorActivation(acoustic=False, irst=False, radar=True),
            doctrine=ShotDoctrine(missile_mode_high_priority="SINGLE_SHOT", missile_mode_standard="SINGLE_SHOT"),
        )
        track = {
            "id": "T-403",
            "type": "JET",
            "iff": "HOSTILE",
            "alive": True,
            "range_m": 3000,
            "speed_mps": 170,
            "position": {"x": 3000, "y": 0},
            "heading_deg": 180,
        }
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=2.0)
        self.assertEqual(payload["tracks"][0]["target_status"], "ASSIGNED")
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=0.5)
        self.assertEqual(payload["tracks"][0]["target_status"], "ENGAGING")
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=2.0)
        self.assertEqual(payload["tracks"][0]["target_status"], "HIT")
        self.assertEqual(payload["tracks"][0]["target_health"], 35)
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=0.75)
        self.assertEqual(payload["tracks"][0]["target_status"], "KILL_ASSESS")
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=0.75)
        self.assertEqual(payload["tracks"][0]["target_status"], "ABORTING")
        messages = [event["message"] for event in payload["events"]]
        self.assertTrue(any("likely aborting attack" in message for message in messages))

    def test_disabled_acoustic_allows_irst_and_radar_only_flow(self):
        engine = ShieldEngine(sensor_activation=SensorActivation(acoustic=False, irst=True, radar=True))
        track = {
            "id": "T-200",
            "type": "JET",
            "iff": "HOSTILE",
            "alive": True,
            "range_m": 2500,
            "speed_mps": 180,
            "position": {"x": 2500, "y": 0},
            "heading_deg": 180,
        }
        self.assertEqual(engine.evaluate_snapshot({"tracks": [track]}, dt=1.0)["summary"]["mode"], "AMBUSH")
        self.assertEqual(engine.evaluate_snapshot({"tracks": [track]}, dt=1.5)["summary"]["mode"], "ACTIVE_TRACK")

        fire_track = dict(track)
        fire_track["range_m"] = 1500
        fire_track["position"] = {"x": 1500, "y": 0}
        self.assertEqual(engine.evaluate_snapshot({"tracks": [fire_track]}, dt=1.5)["summary"]["mode"], "FIRE")

    def test_cruise_missile_low_altitude_delays_radar_handoff(self):
        engine = ShieldEngine(sensor_activation=SensorActivation(acoustic=False, irst=True, radar=True))
        track = {
            "id": "T-901",
            "type": "CRUISE_MISSILE",
            "iff": "HOSTILE",
            "alive": True,
            "range_m": 3000,
            "altitude_m": 250,
            "speed_mps": 240,
            "position": {"x": 3000, "y": 0},
            "heading_deg": 180,
        }
        self.assertEqual(engine.evaluate_snapshot({"tracks": [track]}, dt=1.0)["summary"]["mode"], "AMBUSH")
        self.assertEqual(engine.evaluate_snapshot({"tracks": [track]}, dt=1.0)["summary"]["mode"], "AMBUSH")

    def test_ballistic_missile_reaches_active_track_earlier(self):
        engine = ShieldEngine(sensor_activation=SensorActivation(acoustic=False, irst=False, radar=True))
        track = {
            "id": "T-902",
            "type": "BALLISTIC_MISSILE",
            "iff": "HOSTILE",
            "alive": True,
            "range_m": 5000,
            "altitude_m": 14000,
            "speed_mps": 520,
            "position": {"x": 5000, "y": 0},
            "heading_deg": 180,
        }
        self.assertEqual(engine.evaluate_snapshot({"tracks": [track]}, dt=1.0)["summary"]["mode"], "ACTIVE_TRACK")

    def test_radar_disabled_never_reaches_fire(self):
        engine = ShieldEngine(sensor_activation=SensorActivation(acoustic=True, irst=True, radar=False))
        track = {
            "id": "T-300",
            "type": "MISSILE",
            "iff": "HOSTILE",
            "alive": True,
            "range_m": 1500,
            "speed_mps": 280,
            "position": {"x": 1500, "y": 0},
            "heading_deg": 180,
        }
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=10.0)
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=2.0)
        self.assertNotEqual(payload["summary"]["mode"], "FIRE")
        self.assertEqual(payload["summary"]["sensors"]["radar"], "DISABLED")

    def test_sensor_activation_from_names(self):
        activation = SensorActivation.from_names(["irst", "radar"])
        self.assertFalse(activation.acoustic)
        self.assertTrue(activation.irst)
        self.assertTrue(activation.radar)

    def test_config_loaders_use_environment(self):
        with patch.dict(
            "os.environ",
            {
                "SHIELD_ACTIVE_SENSORS": "irst,radar",
                "SHIELD_MISSILE_CHANNELS": "3",
                "SHIELD_JAMMER_CHANNELS": "2",
                "SHIELD_CIWS_CHANNELS": "1",
                "SHIELD_HIGH_PRIORITY_DOCTRINE": "SINGLE_SHOT",
                "SHIELD_STANDARD_DOCTRINE": "SHOT_LOOK_SHOT",
                "SHIELD_HOLD_FIRE_BELOW_SCORE": "50",
            },
            clear=False,
        ):
            sensors = load_sensor_activation()
            capacity = load_capacity()
            doctrine = load_doctrine()

        self.assertFalse(sensors.acoustic)
        self.assertTrue(sensors.irst)
        self.assertTrue(sensors.radar)
        self.assertEqual(capacity, EngagementCapacity(missile_channels=3, jammer_channels=2, ciws_channels=1))
        self.assertEqual(doctrine.missile_mode_high_priority, "SINGLE_SHOT")
        self.assertEqual(doctrine.missile_mode_standard, "SHOT_LOOK_SHOT")
        self.assertEqual(doctrine.hold_fire_below_score, 50)

    def test_config_loaders_fallback_on_invalid_values(self):
        with patch.dict(
            "os.environ",
            {
                "SHIELD_MISSILE_CHANNELS": "bad",
                "SHIELD_JAMMER_CHANNELS": "-2",
                "SHIELD_HIGH_PRIORITY_DOCTRINE": "INVALID",
            },
            clear=False,
        ):
            capacity = load_capacity()
            doctrine = load_doctrine()

        self.assertEqual(capacity.missile_channels, 2)
        self.assertEqual(capacity.jammer_channels, 0)
        self.assertEqual(doctrine.missile_mode_high_priority, "SHOT_LOOK_SHOT")

    def test_config_loaders_use_file_config_when_env_missing(self):
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "shield.json"
            config_path.write_text(
                """
{
  "active_sensors": ["irst", "radar"],
  "capacity": {
    "missile_channels": 4,
    "jammer_channels": 2,
    "ciws_channels": 3
  },
  "doctrine": {
    "high_priority": "SINGLE_SHOT",
    "standard": "SHOT_LOOK_SHOT",
    "hold_fire_below_score": 52
  }
}
""".strip()
            )
            with patch.object(shield_config, "CONFIG_PATH", config_path), patch.dict("os.environ", {}, clear=True):
                sensors = load_sensor_activation()
                capacity = load_capacity()
                doctrine = load_doctrine()

        self.assertFalse(sensors.acoustic)
        self.assertTrue(sensors.irst)
        self.assertTrue(sensors.radar)
        self.assertEqual(capacity, EngagementCapacity(missile_channels=4, jammer_channels=2, ciws_channels=3))
        self.assertEqual(doctrine.missile_mode_high_priority, "SINGLE_SHOT")
        self.assertEqual(doctrine.missile_mode_standard, "SHOT_LOOK_SHOT")
        self.assertEqual(doctrine.hold_fire_below_score, 52)

    def test_environment_overrides_file_config(self):
        with TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "shield.json"
            config_path.write_text(
                """
{
  "active_sensors": ["acoustic"],
  "capacity": {
    "missile_channels": 1,
    "jammer_channels": 1,
    "ciws_channels": 1
  },
  "doctrine": {
    "high_priority": "SINGLE_SHOT",
    "standard": "SINGLE_SHOT",
    "hold_fire_below_score": 70
  }
}
""".strip()
            )
            with patch.object(shield_config, "CONFIG_PATH", config_path), patch.dict(
                "os.environ",
                {
                    "SHIELD_ACTIVE_SENSORS": "irst,radar",
                    "SHIELD_MISSILE_CHANNELS": "3",
                    "SHIELD_STANDARD_DOCTRINE": "SHOT_LOOK_SHOT",
                    "SHIELD_HOLD_FIRE_BELOW_SCORE": "45",
                },
                clear=True,
            ):
                sensors = load_sensor_activation()
                capacity = load_capacity()
                doctrine = load_doctrine()

        self.assertFalse(sensors.acoustic)
        self.assertTrue(sensors.irst)
        self.assertTrue(sensors.radar)
        self.assertEqual(capacity.missile_channels, 3)
        self.assertEqual(capacity.jammer_channels, 1)
        self.assertEqual(doctrine.missile_mode_high_priority, "SINGLE_SHOT")
        self.assertEqual(doctrine.missile_mode_standard, "SHOT_LOOK_SHOT")
        self.assertEqual(doctrine.hold_fire_below_score, 45)

    def test_doctrine_mode_profiles(self):
        aggressive = doctrine_from_mode("AGGRESSIVE")
        balanced = doctrine_from_mode("BALANCED")
        conservative = doctrine_from_mode("CONSERVATIVE")
        self.assertEqual(aggressive.missile_mode_standard, "SHOT_LOOK_SHOT")
        self.assertEqual(aggressive.hold_fire_below_score, 20)
        self.assertEqual(balanced.hold_fire_below_score, 35)
        self.assertEqual(conservative.hold_fire_below_score, 55)

    def test_channel_limits_allow_only_top_priority_missile_assignment(self):
        engine = ShieldEngine(
            capacity=EngagementCapacity(missile_channels=1, jammer_channels=0, ciws_channels=0),
            sensor_activation=SensorActivation(acoustic=False, irst=False, radar=True),
        )
        snapshot = {
            "tracks": [
                {
                    "id": "T-401",
                    "type": "JET",
                    "iff": "HOSTILE",
                    "alive": True,
                    "range_m": 3000,
                    "speed_mps": 210,
                    "position": {"x": 3000, "y": 0},
                    "heading_deg": 180,
                },
                {
                    "id": "T-402",
                    "type": "JET",
                    "iff": "HOSTILE",
                    "alive": True,
                    "range_m": 3600,
                    "speed_mps": 170,
                    "position": {"x": 3600, "y": 0},
                    "heading_deg": 180,
                },
            ]
        }
        payload = engine.evaluate_snapshot(snapshot, dt=2.0)
        by_id = {track["id"]: track for track in payload["tracks"]}
        self.assertEqual(by_id["T-401"]["assigned_effector"], "SAM")
        self.assertEqual(by_id["T-402"]["assigned_effector"], "MONITOR")

    def test_multiple_batteries_split_assignments_without_double_fire(self):
        engine = ShieldEngine(
            capacity=EngagementCapacity(missile_channels=2, jammer_channels=0, ciws_channels=0),
            sensor_activation=SensorActivation(acoustic=False, irst=False, radar=True),
            sam_batteries=[
                SamBatteryState(
                    id="BTRY-A",
                    name="Battery A",
                    position={"x": 0.0, "y": 0.0},
                    max_range_m=4500.0,
                    ammo_remaining=4,
                    max_channels=1,
                ),
                SamBatteryState(
                    id="BTRY-B",
                    name="Battery B",
                    position={"x": 1800.0, "y": 0.0},
                    max_range_m=4500.0,
                    ammo_remaining=4,
                    max_channels=1,
                ),
            ],
        )
        snapshot = {
            "tracks": [
                {
                    "id": "T-410",
                    "type": "JET",
                    "iff": "HOSTILE",
                    "alive": True,
                    "range_m": 3200,
                    "speed_mps": 210,
                    "position": {"x": 3200, "y": 0},
                    "heading_deg": 180,
                },
                {
                    "id": "T-411",
                    "type": "JET",
                    "iff": "HOSTILE",
                    "alive": True,
                    "range_m": 3000,
                    "speed_mps": 205,
                    "position": {"x": 3000, "y": 200},
                    "heading_deg": 180,
                },
            ]
        }
        payload = engine.evaluate_snapshot(snapshot, dt=2.0)
        by_id = {track["id"]: track for track in payload["tracks"]}
        self.assertEqual(by_id["T-410"]["assigned_effector"], "SAM")
        self.assertEqual(by_id["T-411"]["assigned_effector"], "SAM")
        self.assertNotEqual(by_id["T-410"]["assigned_battery"], by_id["T-411"]["assigned_battery"])
        self.assertEqual(payload["summary"]["ammo"]["sam"], 6)

    def test_high_priority_track_uses_shot_look_shot(self):
        doctrine = ShotDoctrine()
        track = {"type": "MISSILE"}
        self.assertEqual(shot_doctrine_for_track(track, 95, doctrine), "SHOT_LOOK_SHOT")
        self.assertEqual(shot_doctrine_for_track({"type": "DRONE"}, 50, doctrine), "SINGLE_SHOT")

    def test_hold_fire_threshold_prevents_low_score_assignment(self):
        engine = ShieldEngine(
            capacity=EngagementCapacity(missile_channels=2, jammer_channels=1, ciws_channels=1),
            sensor_activation=SensorActivation(acoustic=False, irst=True, radar=False),
            doctrine=ShotDoctrine(hold_fire_below_score=60),
        )
        track = {
            "id": "T-500",
            "type": "DRONE",
            "iff": "HOSTILE",
            "alive": True,
            "range_m": 6500,
            "speed_mps": 70,
            "position": {"x": 6500, "y": 0},
            "heading_deg": 0,
        }
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=2.0)
        self.assertEqual(payload["tracks"][0]["assigned_effector"], "MONITOR")
        self.assertEqual(payload["tracks"][0]["engagement_state"], "TRACKED")

    def test_ammo_is_persistent_after_firing(self):
        engine = ShieldEngine()
        track = {
            "id": "T-800",
            "type": "MISSILE",
            "iff": "HOSTILE",
            "alive": True,
            "range_m": 1500,
            "speed_mps": 280,
            "position": {"x": 1500, "y": 0},
            "heading_deg": 180,
        }
        engine.evaluate_snapshot({"tracks": [track]}, dt=6.0)
        engine.evaluate_snapshot({"tracks": [track]}, dt=2.0)
        engine.evaluate_snapshot({"tracks": [track]}, dt=1.0)
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=1.5)
        self.assertEqual(payload["summary"]["ammo"]["ciws_rounds"], 1550)
        payload = engine.evaluate_snapshot({"tracks": [track]}, dt=0.5)
        self.assertEqual(payload["summary"]["ammo"]["ciws_rounds"], 1425)
        payload = engine.evaluate_snapshot({"tracks": []}, dt=1.0)
        self.assertEqual(payload["summary"]["ammo"]["ciws_rounds"], 1425)


if __name__ == "__main__":
    unittest.main()
