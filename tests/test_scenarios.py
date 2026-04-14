import unittest
from pathlib import Path
from unittest.mock import patch

from pilot.config import load_scenario_name
from scenarios import DEFAULT_SCENARIO_NAME, get_scenario, scenario_names
from scenarios.config_loader import load_scenario_file


class ScenarioTests(unittest.TestCase):
    def test_default_scenario_is_available(self):
        self.assertIn(DEFAULT_SCENARIO_NAME, scenario_names())
        scenario = get_scenario(DEFAULT_SCENARIO_NAME)
        self.assertEqual(scenario.name, DEFAULT_SCENARIO_NAME)
        self.assertGreater(len(scenario.generate_tracks(0)), 0)

    def test_group_saturation_raid_has_multiple_hostile_groups(self):
        scenario = get_scenario("group_saturation_raid")
        tracks = scenario.generate_tracks(0)
        hostile_tracks = [track for track in tracks if track["iff"] == "HOSTILE"]
        hostile_types = {track["type"] for track in hostile_tracks}
        self.assertGreaterEqual(len(hostile_tracks), 8)
        self.assertTrue({"JET", "DRONE", "CRUISE_MISSILE", "BALLISTIC_MISSILE"}.issubset(hostile_types))
        self.assertTrue(any(track["altitude_m"] > 10000 for track in hostile_tracks if track["type"] == "BALLISTIC_MISSILE"))
        self.assertTrue(any(track["altitude_m"] < 500 for track in hostile_tracks if track["type"] == "CRUISE_MISSILE"))

    def test_unknown_scenario_falls_back_to_default(self):
        scenario = get_scenario("missing_scenario")
        self.assertEqual(scenario.name, DEFAULT_SCENARIO_NAME)

    def test_pilot_controller_reads_scenario_from_environment(self):
        with patch.dict("os.environ", {"PILOT_SCENARIO": "group_saturation_raid"}, clear=False):
            scenario_name = load_scenario_name()
        self.assertEqual(scenario_name, "group_saturation_raid")

    def test_json_scenario_file_loads_time_limit(self):
        scenario = load_scenario_file(
            Path("config/scenarios/group_saturation_raid.json")
        )
        self.assertIsNotNone(scenario)
        self.assertEqual(scenario.name, "group_saturation_raid")
        self.assertEqual(scenario.time_limit_s, 240)

    def test_json_scenario_file_supports_priority_bias(self):
        scenario = load_scenario_file(
            Path("config/scenarios/default_layered_raid.json")
        )
        self.assertIsNotNone(scenario)
        cruise = next(template for template in scenario.templates if template.track_id == "T-004")
        self.assertEqual(cruise.priority_bias, 0)
