import unittest

from pilot.truth import PilotTruthModel
from scenarios import get_scenario


class PilotTruthTests(unittest.TestCase):
    def test_destroyed_target_disappears_from_generated_tracks(self):
        model = PilotTruthModel.from_scenario(get_scenario("default_layered_raid"))
        model.apply_snapshot({"tracks": [{"id": "T-004", "target_status": "DESTROYED", "target_health": 0}]})
        tracks = model.generate_tracks(1)
        self.assertFalse(any(track["id"] == "T-004" for track in tracks))

    def test_damaged_aircraft_retreats_after_delay(self):
        model = PilotTruthModel.from_scenario(get_scenario("default_layered_raid"))
        model.current_tick = 2
        model.apply_snapshot({"tracks": [{"id": "T-005", "target_status": "ABORTING", "target_health": 35}]})
        tracks = model.generate_tracks(3)
        initial = next(track for track in tracks if track["id"] == "T-005")
        self.assertFalse(initial["retreating"])
        tracks = model.generate_tracks(6)
        retreater = next(track for track in tracks if track["id"] == "T-005")
        self.assertTrue(retreater["retreating"])
        self.assertEqual(retreater["engagement_state"], "RETREAT")
        self.assertIn(retreater["maneuver_state"], {"RETREAT_TURN", "RETREAT"})

    def test_inbound_track_can_reach_zero_range(self):
        model = PilotTruthModel.from_scenario(get_scenario("default_layered_raid"))
        tracks = model.generate_tracks(140)
        helicopter = next(track for track in tracks if track["id"] == "T-003")
        self.assertEqual(helicopter["range_m"], 0.0)

    def test_hostile_jet_uses_ingress_maneuvering(self):
        model = PilotTruthModel.from_scenario(get_scenario("default_layered_raid"))
        first = next(track for track in model.generate_tracks(4) if track["id"] == "T-005")
        second = next(track for track in model.generate_tracks(5) if track["id"] == "T-005")
        self.assertEqual(first["maneuver_state"], "INGRESS_MANEUVER")
        self.assertNotEqual(first["position"]["y"], second["position"]["y"])
        self.assertNotEqual(first["heading_deg"], second["heading_deg"])

    def test_retreat_turn_is_progressive_before_full_withdrawal(self):
        model = PilotTruthModel.from_scenario(get_scenario("default_layered_raid"))
        model.current_tick = 2
        model.apply_snapshot({"tracks": [{"id": "T-003", "target_status": "ABORTING", "target_health": 40}]})
        turning = next(track for track in model.generate_tracks(6) if track["id"] == "T-003")
        final = next(track for track in model.generate_tracks(9) if track["id"] == "T-003")
        self.assertTrue(turning["retreating"])
        self.assertEqual(turning["maneuver_state"], "RETREAT_TURN")
        self.assertEqual(final["maneuver_state"], "RETREAT")
        self.assertGreater(final["range_m"], turning["range_m"])
