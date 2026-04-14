from __future__ import annotations

import json
from collections import defaultdict

from fastapi import WebSocket

from scenarios import refresh_scenarios
from shared.messages import HubState, registration_message, snapshot_message


class Broker:
    def __init__(self) -> None:
        self.state = HubState.create()
        self.ui_clients: set[WebSocket] = set()
        self.role_clients: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect_ui(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.ui_clients.add(websocket)
        await websocket.send_text(json.dumps(snapshot_message(self.state.snapshot)))

    async def disconnect_ui(self, websocket: WebSocket) -> None:
        self.ui_clients.discard(websocket)

    async def connect_role(self, role: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.role_clients[role].add(websocket)
        await websocket.send_text(json.dumps(registration_message(role, self.state.snapshot)))

    async def disconnect_role(self, role: str, websocket: WebSocket) -> None:
        self.role_clients[role].discard(websocket)

    async def handle_role_message(self, role: str, raw_message: str) -> None:
        message = json.loads(raw_message)
        if message.get("type") != "role_update":
            return

        updated_snapshot = self.state.merge_role_update(role, message.get("payload", {}))
        updated_snapshot = self.state.evaluate_scenario()
        serialized = json.dumps(snapshot_message(updated_snapshot))
        await self._broadcast_ui(serialized)
        await self._broadcast_roles(serialized)

    async def stop_scenario(self) -> None:
        updated_snapshot = self.state.stop_scenario()
        serialized = json.dumps(snapshot_message(updated_snapshot))
        await self._broadcast_ui(serialized)
        await self._broadcast_roles(serialized)

    async def reset_scenario(self, scenario_name: str | None = None) -> None:
        updated_snapshot = self.state.reset_scenario(scenario_name)
        serialized = json.dumps(snapshot_message(updated_snapshot))
        await self._broadcast_ui(serialized)
        await self._broadcast_roles(serialized)

    async def reload_scenario_config(self, scenario_name: str | None = None) -> None:
        refresh_scenarios()
        selected_name = scenario_name or self.state.snapshot["scenario"].get("name")
        updated_snapshot = self.state.reset_scenario(selected_name)
        serialized = json.dumps(snapshot_message(updated_snapshot))
        await self._broadcast_ui(serialized)
        await self._broadcast_roles(serialized)

    async def pause_scenario(self) -> None:
        updated_snapshot = self.state.pause_scenario()
        serialized = json.dumps(snapshot_message(updated_snapshot))
        await self._broadcast_ui(serialized)
        await self._broadcast_roles(serialized)

    async def resume_scenario(self) -> None:
        updated_snapshot = self.state.resume_scenario()
        serialized = json.dumps(snapshot_message(updated_snapshot))
        await self._broadcast_ui(serialized)
        await self._broadcast_roles(serialized)

    async def step_scenario(self) -> None:
        updated_snapshot = self.state.step_scenario()
        serialized = json.dumps(snapshot_message(updated_snapshot))
        await self._broadcast_ui(serialized)
        await self._broadcast_roles(serialized)

    async def set_doctrine_mode(self, doctrine_mode: str) -> None:
        updated_snapshot = self.state.set_doctrine_mode(doctrine_mode)
        serialized = json.dumps(snapshot_message(updated_snapshot))
        await self._broadcast_ui(serialized)
        await self._broadcast_roles(serialized)

    async def _broadcast_ui(self, message: str) -> None:
        stale_clients = []
        for client in self.ui_clients:
            try:
                await client.send_text(message)
            except RuntimeError:
                stale_clients.append(client)
        for client in stale_clients:
            self.ui_clients.discard(client)

    async def _broadcast_roles(self, message: str) -> None:
        for clients in self.role_clients.values():
            stale_clients = []
            for client in clients:
                try:
                    await client.send_text(message)
                except RuntimeError:
                    stale_clients.append(client)
            for client in stale_clients:
                clients.discard(client)
