from __future__ import annotations

import os

from scenarios import DEFAULT_SCENARIO_NAME, get_scenario


def load_scenario_name() -> str:
    requested = os.getenv("PILOT_SCENARIO", DEFAULT_SCENARIO_NAME)
    return get_scenario(requested).name
