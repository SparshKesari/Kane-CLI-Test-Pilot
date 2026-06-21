"""Trigger the GitHub Actions pipeline that runs a TestPilot run.

Used when local_execution=False: the API fires a `workflow_dispatch` for
runner_workflow in runner_repo, passing the run parameters as inputs. The job
(see .github/workflows/pipeline.yml) executes app.ci_runner and streams progress
back to this API.
"""
from __future__ import annotations

import httpx

from .config import get_settings
from .models import Run


async def dispatch_pipeline(run: Run) -> None:
    s = get_settings()
    missing = [name for name, val in (
        ("RUNNER_REPO", s.runner_repo),
        ("GITHUB_TOKEN", s.github_token),
        ("PUBLIC_BASE_URL", s.public_base_url),
    ) if not val]
    if missing:
        raise RuntimeError(
            "CI dispatch is missing required env var(s): " + ", ".join(missing)
            + ". Set them on the API service and redeploy.")

    url = (f"https://api.github.com/repos/{s.runner_repo}"
           f"/actions/workflows/{s.runner_workflow}/dispatches")
    # workflow_dispatch inputs must be strings.
    inputs = {
        "run_id": run.id,
        "repo_url": run.repo_url,
        "target_url": run.target_url or "",
        "mode": run.mode,
        "max_scenarios": str(run.max_scenarios),
        "callback_url": s.public_base_url.rstrip("/"),
    }
    headers = {
        "Authorization": f"Bearer {s.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json={"ref": s.runner_ref, "inputs": inputs},
                              headers=headers)
        # 204 = accepted. Surface the body on failure so misconfig is obvious.
        if r.status_code != 204:
            raise RuntimeError(
                f"workflow_dispatch failed ({r.status_code}): {r.text[:300]}")
