from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from hub.broker import Broker


BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="SAM Simulator Hub")
broker = Broker()
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


class ScenarioControlRequest(BaseModel):
    scenario_name: str | None = None


class DoctrineControlRequest(BaseModel):
    doctrine_mode: str


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.post("/control/stop")
async def stop_simulation() -> JSONResponse:
    await broker.stop_scenario()
    return JSONResponse({"ok": True, "status": broker.state.snapshot["scenario"]["status"]})


@app.post("/control/pause")
async def pause_simulation() -> JSONResponse:
    await broker.pause_scenario()
    scenario = broker.state.snapshot["scenario"]
    return JSONResponse({"ok": True, "execution_state": scenario["execution_state"]})


@app.post("/control/resume")
async def resume_simulation() -> JSONResponse:
    await broker.resume_scenario()
    scenario = broker.state.snapshot["scenario"]
    return JSONResponse({"ok": True, "execution_state": scenario["execution_state"]})


@app.post("/control/step")
async def step_simulation() -> JSONResponse:
    await broker.step_scenario()
    scenario = broker.state.snapshot["scenario"]
    return JSONResponse({"ok": True, "step_budget": scenario["step_budget"]})


@app.post("/control/doctrine")
async def set_doctrine_mode(request: DoctrineControlRequest) -> JSONResponse:
    await broker.set_doctrine_mode(request.doctrine_mode)
    scenario = broker.state.snapshot["scenario"]
    return JSONResponse({"ok": True, "doctrine_mode": scenario["doctrine_mode"]})


@app.post("/control/reset")
async def reset_simulation(request: ScenarioControlRequest) -> JSONResponse:
    await broker.reset_scenario(request.scenario_name)
    scenario = broker.state.snapshot["scenario"]
    return JSONResponse({"ok": True, "status": scenario["status"], "scenario": scenario["name"]})


@app.post("/control/reload")
async def reload_simulation(request: ScenarioControlRequest) -> JSONResponse:
    await broker.reload_scenario_config(request.scenario_name)
    scenario = broker.state.snapshot["scenario"]
    return JSONResponse(
        {
            "ok": True,
            "status": scenario["status"],
            "scenario": scenario["name"],
            "time_limit_s": scenario["time_limit_s"],
        }
    )


@app.get("/control/export/battle-log")
async def export_battle_log() -> JSONResponse:
    return JSONResponse(broker.state.export_battle_log())


@app.get("/control/export/report")
async def export_report() -> JSONResponse:
    snapshot = broker.state.snapshot
    return JSONResponse(
        {
            "scenario": snapshot.get("scenario", {}),
            "report": snapshot.get("report", {}),
        }
    )


@app.websocket("/ws")
async def ui_feed(websocket: WebSocket) -> None:
    await broker.connect_ui(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await broker.disconnect_ui(websocket)


@app.websocket("/ws/role/{role}")
async def role_feed(websocket: WebSocket, role: str) -> None:
    await broker.connect_role(role, websocket)
    try:
        while True:
            raw_message = await websocket.receive_text()
            await broker.handle_role_message(role, raw_message)
    except WebSocketDisconnect:
        await broker.disconnect_role(role, websocket)
