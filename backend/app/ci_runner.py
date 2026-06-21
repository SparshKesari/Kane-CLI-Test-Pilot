"""CI entrypoint: run the full pipeline inside a GitHub Actions job.

    python -m app.ci_runner --run-id ... --repo-url ... --target-url ... \
        --mode auto --max-scenarios 0 --callback-url https://app.onrender.com

It reuses the in-process orchestrator (runner.execute_run) unchanged. Two bridge
tasks connect it to the hosted API:

  • forwarder      — drains the event bus and POSTs events + a run snapshot to
                     {callback}/api/runs/{id}/ingest, so the browser streams live.
  • control poller — GETs {callback}/api/runs/{id}/control for the user's scenario
                     selection / abort and drives the existing local mechanisms.

Auth for both is the shared INGEST_SECRET (a GitHub Actions secret, never logged).
"""
from __future__ import annotations

import argparse
import asyncio
import os

import httpx

from .events import bus
from .models import RUNS, Run
from . import runner as run_mod


def _args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", required=True)
    p.add_argument("--repo-url", required=True)
    p.add_argument("--target-url", default="")
    p.add_argument("--mode", default="auto")
    p.add_argument("--max-scenarios", type=int, default=0)
    p.add_argument("--callback-url", required=True)
    return p.parse_args()


def _log_event(ev: dict) -> None:
    """Mirror an event to stdout so the GitHub Actions log shows live progress
    even if the relay API is unreachable."""
    t = ev.get("type", "log")
    bits = [b for b in (
        ev.get("key"), ev.get("phase"), ev.get("scenario"), ev.get("step"),
        ev.get("status"), ev.get("message"), ev.get("detail"), ev.get("error"),
    ) if b]
    print(f"[{t}] " + " · ".join(str(b) for b in bits)[:200], flush=True)


async def _forwarder(run: Run, q: asyncio.Queue, base: str, secret: str,
                     stop: asyncio.Event) -> None:
    """Drain the bus: mirror every event to stdout and POST it (+ run snapshot)
    to /ingest. A short retry covers a cold-starting API; after repeated failures
    the relay is marked dead so a down API never stalls the pipeline itself."""
    ingest = f"{base}/api/runs/{run.id}/ingest"
    headers = {"Authorization": f"Bearer {secret}"}
    relay = {"dead": False, "fails": 0}

    async with httpx.AsyncClient(timeout=15) as client:
        async def flush(events: list[dict]) -> None:
            if not events or relay["dead"]:
                return
            payload = {"events": events, "run": run.to_dict()}
            for attempt in range(3):
                try:
                    await client.post(ingest, json=payload, headers=headers)
                    relay["fails"] = 0
                    return
                except Exception:  # noqa: BLE001
                    await asyncio.sleep(1.0 * (attempt + 1))
            relay["fails"] += 1
            if relay["fails"] >= 2:
                relay["dead"] = True
                print("[relay] callback API unreachable — continuing without live "
                      "relay (pipeline still runs; PR will still open).", flush=True)

        batch: list[dict] = []
        while not (stop.is_set() and q.empty()):
            try:
                ev = await asyncio.wait_for(q.get(), timeout=0.25)
                _log_event(ev)
                batch.append(ev)
                if len(batch) < 25:
                    continue
            except asyncio.TimeoutError:
                pass
            if batch:
                await flush(batch)
                batch = []
        await flush(batch)
        # one final snapshot so the terminal status/verdict/pr_url is recorded
        await flush([{"type": "run", "status": run.status.value,
                      "verdict": run.verdict, "pr_url": run.pr_url}])


async def _control_poller(run: Run, base: str, secret: str,
                          stop: asyncio.Event) -> None:
    """Poll the API for user control signals and apply them via the existing
    in-process mechanisms (submit_selection / abort_run / abort_scenario)."""
    ctl = f"{base}/api/runs/{run.id}/control"
    headers = {"Authorization": f"Bearer {secret}"}
    applied_abort = False
    seen_scenarios: set[str] = set()

    async with httpx.AsyncClient(timeout=15) as client:
        while not stop.is_set():
            try:
                r = await client.get(ctl, headers=headers)
                c = r.json() if r.status_code == 200 else {}
            except Exception:  # noqa: BLE001
                c = {}
            if c.get("abort") and not applied_abort:
                run_mod.abort_run(run.id)
                applied_abort = True
            for sid in c.get("abort_scenarios", []):
                if sid not in seen_scenarios:
                    run_mod.abort_scenario(run.id, sid)
                    seen_scenarios.add(sid)
            sel = c.get("selection")
            if sel is not None and run.awaiting_selection:
                run_mod.submit_selection(run.id, sel)
            await asyncio.sleep(2)


async def main() -> None:
    a = _args()
    base = a.callback_url.rstrip("/")
    secret = os.environ.get("INGEST_SECRET", "")

    run = Run(repo_url=a.repo_url, target_url=a.target_url,
              mode="human" if a.mode == "human" else "auto",
              max_scenarios=max(0, min(50, a.max_scenarios)))
    run.id = a.run_id          # align with the id the API already handed the UI
    RUNS[run.id] = run

    # Subscribe BEFORE execute_run so no early events are missed.
    q = bus.subscribe(run.id)
    stop = asyncio.Event()
    fwd = asyncio.create_task(_forwarder(run, q, base, secret, stop))
    ctl = asyncio.create_task(_control_poller(run, base, secret, stop))
    try:
        await run_mod.execute_run(run)
    finally:
        stop.set()
        await fwd
        ctl.cancel()
        bus.unsubscribe(run.id, q)


if __name__ == "__main__":
    asyncio.run(main())
