from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field

import websockets

from pilot.config import load_scenario_name
from pilot.truth import PilotTruthModel
from scenarios import DEFAULT_SCENARIO_NAME, get_scenario, refresh_scenarios
from shared.messages import make_event, role_update_message


@dataclass
class HostileController:
    hub_url: str = "ws://127.0.0.1:8000/ws/role/pilot"
    scenario_name: str = DEFAULT_SCENARIO_NAME
    truth_model: PilotTruthModel | None = field(default=None, repr=False)
    scenario_revision: int = 0
    current_tick: int = 0
    scenario_status: str = "RUNNING"
    execution_state: str = "RUNNING"
    step_budget: int = 0
    last_tracks: list[dict] = field(default_factory=list, repr=False)
    last_published_tick: int = 0

    @classmethod
    def from_environment(cls) -> "HostileController":
        refresh_scenarios()
        scenario_name = load_scenario_name()
        hub_url = os.getenv("PILOT_HUB_URL", "ws://127.0.0.1:8000/ws/role/pilot")
        return cls(
            hub_url=hub_url,
            scenario_name=scenario_name,
            truth_model=PilotTruthModel.from_scenario(get_scenario(scenario_name)),
        )

    async def run(self) -> None:
        async with websockets.connect(self.hub_url) as websocket:
            refresh_scenarios()
            registration = json.loads(await websocket.recv())
            scenario = registration.get("payload", {}).get("snapshot", {}).get("scenario", {})
            self.scenario_name = get_scenario(scenario.get("name", self.scenario_name)).name
            self.scenario_revision = int(scenario.get("revision", self.scenario_revision))
            self.scenario_status = scenario.get("status", self.scenario_status)
            self.execution_state = scenario.get("execution_state", self.execution_state)
            self.step_budget = int(scenario.get("step_budget", self.step_budget))
            self.current_tick = int(scenario.get("elapsed_s", self.current_tick))
            self.truth_model = PilotTruthModel.from_scenario(get_scenario(self.scenario_name))
            self.last_tracks = []
            self.last_published_tick = self.current_tick
            consumer = asyncio.create_task(self._consume_snapshots(websocket))
            producer = asyncio.create_task(self._produce_updates(websocket))
            done, pending = await asyncio.wait(
                {consumer, producer}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            for task in done:
                task.result()

    async def _consume_snapshots(self, websocket) -> None:
        while True:
            message = json.loads(await websocket.recv())
            if message.get("type") != "snapshot":
                continue
            payload = message.get("payload", {})
            scenario = payload.get("scenario", {})
            snapshot_scenario_name = scenario.get("name", self.scenario_name)
            snapshot_revision = int(scenario.get("revision", self.scenario_revision))
            self.scenario_status = scenario.get("status", self.scenario_status)
            self.execution_state = scenario.get("execution_state", self.execution_state)
            self.step_budget = int(scenario.get("step_budget", self.step_budget))
            if snapshot_revision != self.scenario_revision or snapshot_scenario_name != self.scenario_name:
                refresh_scenarios()
                self.scenario_name = get_scenario(snapshot_scenario_name).name
                self.scenario_revision = snapshot_revision
                self.current_tick = int(scenario.get("elapsed_s", 0))
                self.truth_model = PilotTruthModel.from_scenario(get_scenario(self.scenario_name))
                self.last_tracks = []
                self.last_published_tick = self.current_tick
            if self.truth_model is not None:
                self.truth_model.apply_snapshot(payload)

    async def _produce_updates(self, websocket) -> None:
        while True:
            scenario = get_scenario(self.scenario_name)
            truth_model = self.truth_model or PilotTruthModel.from_scenario(scenario)
            if self.truth_model is None:
                self.truth_model = truth_model
            should_advance = self.scenario_status == "RUNNING" and (
                self.execution_state == "RUNNING" or self.step_budget > 0
            )
            if should_advance:
                elapsed_s = self.current_tick
                tracks = truth_model.generate_tracks(self.current_tick)
                self.last_tracks = tracks
                self.last_published_tick = elapsed_s
            else:
                elapsed_s = self.last_published_tick
                tracks = self.last_tracks
            outbound_step_budget = self.step_budget
            if should_advance and self.execution_state == "PAUSED" and self.step_budget > 0:
                outbound_step_budget -= 1
                self.step_budget = outbound_step_budget
            payload = {
                "tracks": tracks,
                "scenario": {
                    "name": scenario.name,
                    "status": self.scenario_status,
                    "execution_state": self.execution_state,
                    "elapsed_s": elapsed_s,
                    "time_limit_s": scenario.time_limit_s,
                    "revision": self.scenario_revision,
                    "step_budget": outbound_step_budget,
                },
                "events": [
                    make_event(
                        "info",
                        "pilot",
                        f"Scenario {scenario.name} advanced to tick {elapsed_s} with {len(tracks)} tracks.",
                    )
                ],
            }
            await websocket.send(json.dumps(role_update_message("pilot", payload)))
            if should_advance:
                self.current_tick += 1
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(HostileController.from_environment().run())
