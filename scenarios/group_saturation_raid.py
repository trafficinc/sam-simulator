from __future__ import annotations

from scenarios.base import HostileTemplate, ScenarioDefinition


SCENARIO = ScenarioDefinition(
    name="group_saturation_raid",
    time_limit_s=240,
    templates=(
        HostileTemplate("G-101", "JET", "HOSTILE", 9800.0, 6200.0, 210.0, 0.15, 165.0, 0.05, 20.0),
        HostileTemplate("G-102", "JET", "HOSTILE", 9600.0, 5900.0, 205.0, 0.32, 160.0, 0.05, 25.0),
        HostileTemplate("G-103", "JET", "HOSTILE", 9400.0, 5700.0, 195.0, 0.48, 150.0, 0.05, 18.0),
        HostileTemplate("G-201", "DRONE", "HOSTILE", 7200.0, 700.0, 85.0, 1.10, 120.0, 0.10, 5.0),
        HostileTemplate("G-202", "DRONE", "HOSTILE", 7000.0, 650.0, 82.0, 1.24, 118.0, 0.10, 8.0),
        HostileTemplate("G-203", "DRONE", "HOSTILE", 6800.0, 600.0, 80.0, 1.38, 116.0, 0.10, 12.0),
        HostileTemplate("G-301", "CRUISE_MISSILE", "HOSTILE", 6100.0, 220.0, 245.0, 2.00, 230.0, 0.04, 38.0),
        HostileTemplate("G-302", "BALLISTIC_MISSILE", "HOSTILE", 5900.0, 14000.0, 520.0, 2.12, 225.0, 0.04, 42.0),
        HostileTemplate("G-401", "HELICOPTER", "FRIEND", 8600.0, 950.0, 70.0, 3.40, 15.0, 0.04, 0.0),
    ),
)
