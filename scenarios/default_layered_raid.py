from __future__ import annotations

from scenarios.base import HostileTemplate, ScenarioDefinition


SCENARIO = ScenarioDefinition(
    name="default_layered_raid",
    time_limit_s=180,
    templates=(
        HostileTemplate("T-001", "JET", "FRIEND", 9200.0, 5200.0, 120.0, 0.10, 15.0, 0.04, 20.0),
        HostileTemplate("T-002", "DRONE", "HOSTILE", 8600.0, 900.0, 95.0, 0.90, 110.0, 0.10, 5.0, alive_until_tick=22),
        HostileTemplate("T-003", "HELICOPTER", "HOSTILE", 7900.0, 1200.0, 75.0, 1.60, 65.0, 0.07, 15.0),
        HostileTemplate("T-004", "CRUISE_MISSILE", "HOSTILE", 6200.0, 250.0, 240.0, 2.10, 210.0, 0.03, 40.0),
        HostileTemplate("T-005", "JET", "HOSTILE", 9400.0, 6100.0, 185.0, 2.90, 125.0, 0.06, 10.0),
        HostileTemplate("T-006", "HELICOPTER", "FRIEND", 8800.0, 1000.0, 70.0, 3.50, 20.0, 0.05, 0.0),
    ),
)
