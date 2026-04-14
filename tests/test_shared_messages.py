import unittest

from shared.messages import (
    HubState,
    SCHEMA_VERSION,
    make_role_update_payload,
    registration_message,
    role_update_message,
    snapshot_message,
)


class SharedMessageTests(unittest.TestCase):
    def test_snapshot_message_includes_payload_metadata(self):
        message = snapshot_message({"summary": {}, "tracks": [], "events": [], "ciws": {}, "passive_tracking": {}})
        self.assertEqual(message["schema_version"], SCHEMA_VERSION)
        self.assertEqual(message["payload_type"], "snapshot")
        self.assertEqual(message["payload"]["meta"]["schema_version"], SCHEMA_VERSION)

    def test_role_update_message_normalizes_missing_sections(self):
        message = role_update_message("pilot", {"tracks": [{"id": "T-1"}]})
        payload = message["payload"]
        self.assertEqual(payload["payload_type"], "role_update")
        self.assertEqual(payload["tracks"], [{"id": "T-1"}])
        self.assertEqual(payload["summary"], {})
        self.assertEqual(payload["events"], [])

    def test_registration_message_wraps_snapshot(self):
        message = registration_message("pilot", {"summary": {}, "tracks": [], "events": [], "ciws": {}, "passive_tracking": {}})
        self.assertEqual(message["type"], "hub_registered")
        self.assertEqual(message["payload_type"], "registration")
        self.assertEqual(message["payload"]["role"], "pilot")
        self.assertEqual(message["payload"]["snapshot"]["meta"]["payload_type"], "snapshot")

    def test_hub_state_merges_normalized_role_update(self):
        state = HubState.create()
        payload = make_role_update_payload(
            tracks=[{"id": "T-100", "type": "JET", "alive": True}],
            summary={"mode": "TRIPWIRE"},
        )
        snapshot = state.merge_role_update("pilot", payload)
        self.assertEqual(snapshot["summary"]["mode"], "TRIPWIRE")
        self.assertEqual(snapshot["summary"]["track_count"], 1)
        self.assertEqual(snapshot["tracks"][0]["id"], "T-100")

    def test_initial_snapshot_includes_defended_zones(self):
        state = HubState.create()
        zones = state.snapshot["defended_zones"]
        self.assertEqual([zone["type"] for zone in zones], ["BASE", "AIRPORT", "CITY"])
        self.assertTrue(all(zone["health"] == 100 for zone in zones))
        self.assertEqual(state.snapshot["sam_batteries"][0]["id"], "BTRY-A")
        self.assertEqual(
            state.snapshot["summary"]["ammo"]["sam"],
            sum(int(battery["ammo"]) for battery in state.snapshot["sam_batteries"]),
        )
        self.assertEqual(state.snapshot["battle_log"], [])

    def test_hub_state_generates_success_report(self):
        state = HubState.create()
        state.merge_role_update(
            "pilot",
            make_role_update_payload(
                tracks=[
                    {
                        "id": "T-200",
                        "type": "JET",
                        "iff": "HOSTILE",
                        "alive": True,
                        "target_status": "DESTROYED",
                    }
                ],
                scenario={"name": "demo", "status": "RUNNING", "elapsed_s": 42},
            ),
        )
        snapshot = state.evaluate_scenario()
        self.assertEqual(snapshot["scenario"]["status"], "SUCCESS")
        self.assertEqual(snapshot["report"]["outcome"], "SUCCESS")
        self.assertEqual(snapshot["report"]["metrics"]["hostiles_destroyed"], 1)

    def test_zone_health_drops_when_hostile_enters_zone(self):
        state = HubState.create()
        state.merge_role_update(
            "pilot",
            make_role_update_payload(
                tracks=[
                    {
                        "id": "T-901",
                        "type": "MISSILE",
                        "iff": "HOSTILE",
                        "alive": True,
                        "position": {"x": 0.0, "y": 0.0},
                        "range_m": 100.0,
                        "target_status": "TRACKED",
                    }
                ]
            ),
        )
        snapshot = state.evaluate_scenario()
        base_zone = next(zone for zone in snapshot["defended_zones"] if zone["type"] == "BASE")
        self.assertEqual(base_zone["health"], 30)
        self.assertEqual(base_zone["status"], "DAMAGED")

    def test_zone_damage_repeats_while_hostile_remains_inside_zone(self):
        state = HubState.create()
        payload = make_role_update_payload(
            tracks=[
                {
                    "id": "T-902",
                    "type": "HELICOPTER",
                    "iff": "HOSTILE",
                    "alive": True,
                    "position": {"x": 0.0, "y": 0.0},
                    "range_m": 0.0,
                    "target_status": "TRACKED",
                }
            ],
            scenario={"elapsed_s": 0},
        )
        state.merge_role_update("pilot", payload)
        snapshot = state.evaluate_scenario()
        base_zone = next(zone for zone in snapshot["defended_zones"] if zone["type"] == "BASE")
        self.assertEqual(base_zone["health"], 65)

        state.merge_role_update(
            "pilot",
            make_role_update_payload(
                tracks=payload["tracks"],
                scenario={"elapsed_s": 3},
            ),
        )
        snapshot = state.evaluate_scenario()
        base_zone = next(zone for zone in snapshot["defended_zones"] if zone["type"] == "BASE")
        self.assertEqual(base_zone["health"], 30)

    def test_pilot_update_prunes_tracks_absent_from_truth_feed(self):
        state = HubState.create()
        state.merge_role_update(
            "pilot",
            make_role_update_payload(
                tracks=[
                    {"id": "T-100", "type": "JET", "alive": True},
                    {"id": "T-101", "type": "DRONE", "alive": True},
                ]
            ),
        )
        snapshot = state.merge_role_update(
            "pilot",
            make_role_update_payload(tracks=[{"id": "T-101", "type": "DRONE", "alive": True}]),
        )
        self.assertEqual([track["id"] for track in snapshot["tracks"]], ["T-101"])

    def test_stop_scenario_generates_report(self):
        state = HubState.create()
        snapshot = state.stop_scenario()
        self.assertEqual(snapshot["scenario"]["status"], "STOPPED")
        self.assertEqual(snapshot["report"]["outcome"], "STOPPED")

    def test_reset_scenario_changes_name_and_revision(self):
        state = HubState.create()
        original_revision = state.snapshot["scenario"]["revision"]
        snapshot = state.reset_scenario("group_saturation_raid")
        self.assertEqual(snapshot["scenario"]["name"], "group_saturation_raid")
        self.assertEqual(snapshot["scenario"]["status"], "RUNNING")
        self.assertEqual(snapshot["scenario"]["time_limit_s"], 240)
        self.assertEqual(snapshot["scenario"]["revision"], original_revision + 1)
        self.assertIn("group_saturation_raid", snapshot["scenario"]["available_scenarios"])

    def test_pause_resume_and_step_update_execution_state(self):
        state = HubState.create()
        snapshot = state.pause_scenario()
        self.assertEqual(snapshot["scenario"]["execution_state"], "PAUSED")
        snapshot = state.step_scenario()
        self.assertEqual(snapshot["scenario"]["step_budget"], 1)
        snapshot = state.resume_scenario()
        self.assertEqual(snapshot["scenario"]["execution_state"], "RUNNING")
        self.assertEqual(snapshot["scenario"]["step_budget"], 0)

    def test_doctrine_mode_can_be_set(self):
        state = HubState.create()
        snapshot = state.set_doctrine_mode("AGGRESSIVE")
        self.assertEqual(snapshot["scenario"]["doctrine_mode"], "AGGRESSIVE")
        self.assertIn("AGGRESSIVE", snapshot["scenario"]["available_doctrine_modes"])

    def test_report_retains_destroyed_hostile_history_after_truth_track_disappears(self):
        state = HubState.create()
        state.merge_role_update(
            "pilot",
            make_role_update_payload(
                tracks=[
                    {
                        "id": "T-300",
                        "type": "JET",
                        "iff": "HOSTILE",
                        "alive": True,
                        "target_health": 100,
                    }
                ]
            ),
        )
        state.merge_role_update(
            "shield",
            make_role_update_payload(
                tracks=[
                    {
                        "id": "T-300",
                        "iff": "HOSTILE",
                        "target_status": "DESTROYED",
                        "target_health": 0,
                        "engagement_state": "KILL_CONFIRMED",
                    }
                ]
            ),
        )
        state.merge_role_update("pilot", make_role_update_payload(tracks=[]))
        report = state.generate_report("SUCCESS", "All hostile tracks neutralized or forced to retreat.")
        history = {item["id"]: item for item in report["hostile_history"]}
        self.assertIn("T-300", history)
        self.assertEqual(history["T-300"]["final_status"], "DESTROYED")
        self.assertEqual(report["metrics"]["hostiles_destroyed"], 1)

    def test_battle_log_persists_role_events(self):
        state = HubState.create()
        state.merge_role_update(
            "shield",
            make_role_update_payload(
                events=[
                    {
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "level": "info",
                        "category": "engagement",
                        "message": "Missile launched at T-004.",
                    }
                ],
                scenario={"elapsed_s": 12},
            ),
        )
        battle_log = state.snapshot["battle_log"]
        self.assertEqual(len(battle_log), 1)
        self.assertEqual(battle_log[0]["source"], "shield")
        self.assertEqual(battle_log[0]["time_s"], 12)
        self.assertEqual(battle_log[0]["message"], "Missile launched at T-004.")
        self.assertEqual(battle_log[0]["category"], "WEAPON_RELEASE")
        self.assertEqual(battle_log[0]["target_id"], "T-004")

    def test_reset_scenario_clears_prior_battle_log_and_seeds_reset_entry(self):
        state = HubState.create()
        state.merge_role_update(
            "shield",
            make_role_update_payload(
                events=[
                    {
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "level": "info",
                        "category": "engagement",
                        "message": "Opening fire with CIWS on T-005.",
                    }
                ]
            ),
        )
        snapshot = state.reset_scenario("group_saturation_raid")
        self.assertEqual(len(snapshot["battle_log"]), 1)
        self.assertEqual(snapshot["battle_log"][0]["source"], "hub")
        self.assertIn("Scenario reset to group_saturation_raid", snapshot["battle_log"][0]["message"])

    def test_battle_log_filters_out_noise_events(self):
        state = HubState.create()
        state.merge_role_update(
            "shield",
            make_role_update_payload(
                events=[
                    {
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "level": "info",
                        "category": "assignment",
                        "message": "No hostile tracks require engagement.",
                    },
                    {
                        "timestamp": "2026-01-01T00:00:01+00:00",
                        "level": "critical",
                        "category": "engagement",
                        "message": "T-004 rounds on target.",
                    },
                    {
                        "timestamp": "2026-01-01T00:00:02+00:00",
                        "level": "warning",
                        "category": "engagement",
                        "message": "T-004 target hit by missile intercept.",
                    },
                ],
                scenario={"elapsed_s": 18},
            ),
        )
        battle_log = state.snapshot["battle_log"]
        self.assertEqual(len(battle_log), 1)
        self.assertEqual(battle_log[0]["category"], "HIT")
        self.assertEqual(battle_log[0]["target_id"], "T-004")


if __name__ == "__main__":
    unittest.main()
