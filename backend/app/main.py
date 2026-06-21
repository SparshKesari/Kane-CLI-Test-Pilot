from __future__ import annotations

import asyncio

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import ci_state
from .config import get_settings
from .events import bus
from .models import RUNS, Run, RunStatus
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


class IngestBody(BaseModel):
    events: list[dict] = []
    run: dict | None = None     # full run snapshot (to_dict) from the CI job


def _auth_ci(authorization: str) -> None:
    """Authorize a CI → API call with the shared INGEST_SECRET."""
    expected = settings.ingest_secret
    if not expected or authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="invalid ingest secret")


def _run_view(run_id: str) -> dict:
    """Current view of a run — the CI snapshot if present, else the local Run."""
    snap = ci_state.get_snapshot(run_id)
    if snap is not None:
        return snap
    run = RUNS.get(run_id)
    return run.to_dict() if run else {"error": "not_found"}


@app.get("/api/health")
def health():
    return {"ok": True, "demo_mode": settings.demo_mode,
            "local_execution": settings.local_execution}


@app.get("/api/runs")
def list_runs():
    seen: set[str] = set()
    out: list[dict] = []
    for rid, snap in ci_state.SNAPSHOTS.items():
        out.append(snap)
        seen.add(rid)
    for r in RUNS.values():
        if r.id not in seen:
            out.append(r.to_dict())
    out.sort(key=lambda d: -d.get("created_at", 0))
    return out


@app.post("/api/runs")
async def create_run(body: CreateRun):
    run = Run(
        repo_url=body.repo_url.strip(),
        target_url=body.target_url.strip(),
        max_scenarios=max(0, min(50, body.max_scenarios)),  # 0 = auto; else hard cap
        mode="human" if body.mode == "human" else "auto",
    )
    RUNS[run.id] = run

    if settings.local_execution:
        asyncio.create_task(execute_run(run))
    else:
        # Hand execution to a GitHub Actions job; it streams progress back.
        run.status = RunStatus.running
        ci_state.set_snapshot(run.id, run.to_dict())
        try:
            from .dispatch import dispatch_pipeline
            await dispatch_pipeline(run)
            await bus.publish(run.id, "log", phase="P1",
                              message="Queued — starting CI runner…")
        except Exception as exc:  # noqa: BLE001
            run.status = RunStatus.error
            ci_state.set_snapshot(run.id, run.to_dict())
            await bus.publish(run.id, "error",
                              message=f"Could not start CI run: {exc}")
    return _run_view(run.id)


# --------------------------------------------------------------------------- #
# CI bridge — the GitHub Actions job streams events/snapshots here and polls
# for the user's control signals (selection / abort).
# --------------------------------------------------------------------------- #
@app.post("/api/runs/{run_id}/ingest")
async def ingest(run_id: str, body: IngestBody, authorization: str = Header(default="")):
    _auth_ci(authorization)
    if body.run is not None:
        ci_state.set_snapshot(run_id, body.run)   # snapshot first…
    for ev in body.events:                         # …then re-stream to browsers
        type_ = ev.get("type", "log")
        payload = {k: v for k, v in ev.items() if k not in ("type", "ts")}
        await bus.publish(run_id, type_, **payload)
    return {"ok": True}


@app.get("/api/runs/{run_id}/control")
def control(run_id: str, authorization: str = Header(default="")):
    _auth_ci(authorization)
    return ci_state.control_for(run_id)


@app.post("/api/runs/{run_id}/select")
async def select_scenarios(run_id: str, body: Selection):
    """Human-in-the-loop: deliver the user's chosen scenarios to a paused run."""
    if settings.local_execution:
        from .runner import submit_selection
        ok = submit_selection(run_id, body.scenario_ids)
    else:
        ci_state.set_selection(run_id, body.scenario_ids)
        ok = True
    return {"ok": ok, "selected": len(body.scenario_ids)}


@app.post("/api/runs/{run_id}/abort")
async def abort(run_id: str, body: Abort):
    """Abort one scenario — skip it if queued, kill its kane-cli run if in-flight."""
    if settings.local_execution:
        from .runner import abort_scenario
        killed = abort_scenario(run_id, body.scenario_id)
    else:
        ci_state.request_abort_scenario(run_id, body.scenario_id)
        killed = False
    return {"ok": True, "killed_in_flight": killed}


@app.post("/api/runs/{run_id}/abort_run")
async def abort_one_run(run_id: str):
    """Abort a whole run — stop it, no PR."""
    if settings.local_execution:
        from .runner import abort_run
        killed = abort_run(run_id)
    else:
        ci_state.request_abort(run_id)
        killed = 0
    return {"ok": True, "killed_in_flight": killed}


@app.post("/api/runs/abort_all")
async def abort_all():
    """Abort every in-progress run."""
    if settings.local_execution:
        from .runner import abort_all_runs
        return {"ok": True, "aborted_runs": abort_all_runs()}
    ids = set(ci_state.SNAPSHOTS.keys()) | {r.id for r in RUNS.values()}
    for rid in ids:
        ci_state.request_abort(rid)
    return {"ok": True, "aborted_runs": len(ids)}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    return _run_view(run_id)


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
