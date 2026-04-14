from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field

import websockets

from shared.messages import make_event, role_update_message
from shield.config import load_capacity, load_doctrine, load_sensor_activation
from shield.logic import EngagementCapacity, SensorActivation, ShieldEngine, ShotDoctrine, doctrine_from_mode


@dataclass
class ShieldController:
    hub_url: str = "ws://127.0.0.1:8000/ws/role/shield"
    engine: ShieldEngine = field(default_factory=ShieldEngine)
    scenario_revision: int = 0
    scenario_status: str = "RUNNING"
    execution_state: str = "RUNNING"
    last_processed_elapsed_s: int = -1
    doctrine_mode: str = "BALANCED"
    sensor_activation: SensorActivation = field(default_factory=SensorActivation)
    capacity: EngagementCapacity = field(default_factory=EngagementCapacity)
    doctrine: ShotDoctrine = field(default_factory=ShotDoctrine)

    @classmethod
    def from_environment(cls) -> "ShieldController":
        sensor_activation = load_sensor_activation()
        capacity = load_capacity()
        doctrine = load_doctrine()
        hub_url = os.getenv("SHIELD_HUB_URL", "ws://127.0.0.1:8000/ws/role/shield")
        return cls(
            hub_url=hub_url,
            engine=ShieldEngine(
                sensor_activation=sensor_activation,
                capacity=capacity,
                doctrine=doctrine,
            ),
            sensor_activation=sensor_activation,
            capacity=capacity,
            doctrine=doctrine,
        )

    async def run(self) -> None:
        async with websockets.connect(self.hub_url) as websocket:
            registration = json.loads(await websocket.recv())
            snapshot = registration["payload"]["snapshot"]
            scenario = snapshot.get("scenario", {})
            self.scenario_revision = int(scenario.get("revision", self.scenario_revision))
            self.scenario_status = scenario.get("status", self.scenario_status)
            self.execution_state = scenario.get("execution_state", self.execution_state)
            self.doctrine_mode = scenario.get("doctrine_mode", self.doctrine_mode)
            self.last_processed_elapsed_s = int(scenario.get("elapsed_s", -1))
            self.doctrine = doctrine_from_mode(self.doctrine_mode)
            self.engine = ShieldEngine(
                sensor_activation=self.sensor_activation,
                capacity=self.capacity,
                doctrine=self.doctrine,
            )
            producer = asyncio.create_task(self._periodic_status_push(websocket, snapshot))
            consumer = asyncio.create_task(self._consume_snapshots(websocket))
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
            if message["payload"].get("meta", {}).get("last_role") == "shield":
                continue
            scenario = message["payload"].get("scenario", {})
            snapshot_revision = int(scenario.get("revision", self.scenario_revision))
            self.scenario_status = scenario.get("status", self.scenario_status)
            self.execution_state = scenario.get("execution_state", self.execution_state)
            doctrine_mode = scenario.get("doctrine_mode", self.doctrine_mode)
            elapsed_s = int(scenario.get("elapsed_s", self.last_processed_elapsed_s))
            if snapshot_revision != self.scenario_revision or doctrine_mode != self.doctrine_mode:
                self.scenario_revision = snapshot_revision
                self.doctrine_mode = doctrine_mode
                self.doctrine = doctrine_from_mode(self.doctrine_mode)
                self.last_processed_elapsed_s = -1
                self.engine = ShieldEngine(
                    sensor_activation=self.sensor_activation,
                    capacity=self.capacity,
                    doctrine=self.doctrine,
                )
            if self.scenario_status != "RUNNING":
                continue
            if self.execution_state != "RUNNING" and elapsed_s == self.last_processed_elapsed_s:
                continue
            payload = self.engine.evaluate_snapshot(message["payload"])
            self.last_processed_elapsed_s = elapsed_s
            await websocket.send(json.dumps(role_update_message("shield", payload)))

    async def _periodic_status_push(self, websocket, snapshot: dict) -> None:
        payload = self.engine.evaluate_snapshot(snapshot)
        await websocket.send(json.dumps(role_update_message("shield", payload)))
        while True:
            await asyncio.sleep(5)
            keepalive = {
                "events": [make_event("info", "shield", "Shield heartbeat and doctrine check.")],
            }
            await websocket.send(json.dumps(role_update_message("shield", keepalive)))


if __name__ == "__main__":
    asyncio.run(ShieldController.from_environment().run())
