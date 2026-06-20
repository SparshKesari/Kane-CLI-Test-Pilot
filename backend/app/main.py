from __future__ import annotations

import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import get_settings
from .events import bus
from .models import RUNS, Run
from .runner import execute_run

settings = get_settings()
app = FastAPI(title="KaneCLI TestPilot")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:3000"],
    # Allow any Render-hosted frontend so the exact URL needn't be hardcoded.
    allow_origin_regex=r"https://.*\.onrender\.com",
    allow_methods=["*"], allow_headers=["*"],
)


class CreateRun(BaseModel):
    repo_url: str
    target_url: str = ""   # the live app Kane drives — provided per run
    max_scenarios: int = 0   # 0 = auto (greenfield/gap-fill mode picks the budget)
    mode: str = "auto"       # "auto" | "human" (human-in-the-loop selection)


class Selection(BaseModel):
    scenario_ids: list[str]


class Abort(BaseModel):
    scenario_id: str


@app.get("/api/health")
def health():
    return {"ok": True, "demo_mode": settings.demo_mode}


@app.get("/api/runs")
def list_runs():
    return [r.to_dict() for r in sorted(RUNS.values(), key=lambda r: -r.created_at)]


@app.post("/api/runs")
async def create_run(body: CreateRun):
    run = Run(
        repo_url=body.repo_url.strip(),
        target_url=body.target_url.strip(),
        max_scenarios=max(0, min(50, body.max_scenarios)),  # 0 = auto; else hard cap
        mode="human" if body.mode == "human" else "auto",
    )
    RUNS[run.id] = run
    asyncio.create_task(execute_run(run))
    return run.to_dict()


@app.post("/api/runs/{run_id}/select")
async def select_scenarios(run_id: str, body: Selection):
    """Human-in-the-loop: deliver the user's chosen scenarios to a paused run."""
    from .runner import submit_selection
    ok = submit_selection(run_id, body.scenario_ids)
    return {"ok": ok, "selected": len(body.scenario_ids)}


@app.post("/api/runs/{run_id}/abort")
async def abort(run_id: str, body: Abort):
    """Abort one scenario — skip it if queued, kill its kane-cli run if in-flight."""
    from .runner import abort_scenario
    killed = abort_scenario(run_id, body.scenario_id)
    return {"ok": True, "killed_in_flight": killed}


@app.post("/api/runs/{run_id}/abort_run")
async def abort_one_run(run_id: str):
    """Abort a whole run — stop it, no PR."""
    from .runner import abort_run
    killed = abort_run(run_id)
    return {"ok": True, "killed_in_flight": killed}


@app.post("/api/runs/abort_all")
async def abort_all():
    """Abort every in-progress run."""
    from .runner import abort_all_runs
    return {"ok": True, "aborted_runs": abort_all_runs()}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = RUNS.get(run_id)
    return run.to_dict() if run else {"error": "not_found"}


@app.websocket("/api/runs/{run_id}/events")
async def ws_events(websocket: WebSocket, run_id: str):
    await websocket.accept()
    q = bus.subscribe(run_id)
    try:
        for ev in bus.history(run_id):      # replay so late joiners catch up
            await websocket.send_json(ev)
        while True:
            ev = await q.get()
            await websocket.send_json(ev)
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(run_id, q)
