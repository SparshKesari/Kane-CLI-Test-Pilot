"""State for CI-executed runs.

When the pipeline runs in a GitHub Actions job (local_execution=False), the API
no longer owns the Run object — the CI job does. The job streams two things back
to the API:

  • events    → re-published on the WebSocket bus so the browser updates live
  • snapshots → the full run dict, so GET /api/runs/{id} stays correct (the
                frontend refetches it on run/tests/metrics/awaiting_selection)

and polls the API for control signals (the user's scenario selection or abort).
This module is the in-memory bridge for both directions.
"""
from __future__ import annotations

# run_id → latest full run dict (from to_dict()), pushed by the CI job.
SNAPSHOTS: dict[str, dict] = {}

# run_id → {"abort": bool, "abort_scenarios": [ids], "selection": [ids] | None}
CONTROL: dict[str, dict] = {}


def set_snapshot(run_id: str, run_dict: dict) -> None:
    SNAPSHOTS[run_id] = run_dict


def get_snapshot(run_id: str) -> dict | None:
    return SNAPSHOTS.get(run_id)


def control_for(run_id: str) -> dict:
    return CONTROL.get(run_id, {})


def request_abort(run_id: str) -> None:
    CONTROL.setdefault(run_id, {})["abort"] = True


def request_abort_scenario(run_id: str, scenario_id: str) -> None:
    CONTROL.setdefault(run_id, {}).setdefault("abort_scenarios", []).append(scenario_id)


def set_selection(run_id: str, scenario_ids: list[str]) -> None:
    CONTROL.setdefault(run_id, {})["selection"] = list(scenario_ids)
