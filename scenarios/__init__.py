from __future__ import annotations

from scenarios.base import ScenarioDefinition
from scenarios.config_loader import FALLBACK_SCENARIOS, load_scenarios


SCENARIOS: dict[str, ScenarioDefinition] = load_scenarios()

DEFAULT_SCENARIO_NAME = next(iter(SCENARIOS), next(iter(FALLBACK_SCENARIOS)))


def refresh_scenarios() -> dict[str, ScenarioDefinition]:
    global SCENARIOS, DEFAULT_SCENARIO_NAME
    SCENARIOS = load_scenarios()
    DEFAULT_SCENARIO_NAME = next(iter(SCENARIOS), next(iter(FALLBACK_SCENARIOS)))
    return SCENARIOS


def get_scenario(name: str | None) -> ScenarioDefinition:
    if not name:
        return SCENARIOS[DEFAULT_SCENARIO_NAME]
    return SCENARIOS.get(name, SCENARIOS[DEFAULT_SCENARIO_NAME])


def scenario_names() -> list[str]:
    return sorted(SCENARIOS)
