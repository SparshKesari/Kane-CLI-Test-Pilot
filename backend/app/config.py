from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    demo_mode: bool = True

    github_token: str = ""
    lt_username: str = ""
    lt_access_key: str = ""
    anthropic_api_key: str = ""
    agent_model: str = "claude-sonnet-4-6"

    workspace_dir: str = "./.workspaces"
    frontend_origin: str = "http://localhost:3000"

    # "as_is"  → commit Kane's testmu-dialect Playwright-Python export verbatim (no key needed)
    # "vanilla" → LLM agent translates to dependency-free Playwright (needs ANTHROPIC_API_KEY)
    test_style: str = "as_is"

    # P4 scenario budget by mode. A run is "greenfield" when the repo has at most
    # `greenfield_max_existing` existing UI/e2e tests → propose broad coverage;
    # otherwise "gap-fill" → propose only the missing cases. A per-run
    # max_scenarios > 0 overrides these caps.
    scenario_budget_greenfield: int = 20
    scenario_budget_gapfill: int = 10
    greenfield_max_existing: int = 2

    # Concurrent live Kane verifications in P6 (each scenario is one Kane run).
    # Higher = faster wall-clock. For LOCAL headless runs the hard ceiling is ~8:
    # Kane drives Chrome on CDP ports 9222-9230 (9 ports), so keep this ≤ 8 or
    # runs start failing with "All CDP ports in use". Raise via KANE_CONCURRENCY.
    kane_concurrency: int = 6

    # Wall-clock cap (seconds) on a single kane-cli run before it's killed and
    # treated as a failure. Lower = slow/hung flows fail faster.
    kane_timeout: int = 180

    # Kane's agent is nondeterministic — a flow can fail to converge on one run
    # and succeed on the next. Retry "could not observe" failures up to this many
    # total attempts before discarding, so flakiness doesn't drop verifiable tests.
    kane_attempts: int = 2

    # Determinism replays per scenario in P6. Each replay is a full Kane cloud run.
    # Default 0 = trust Kane's live verify (fast, reliable). 1+ = extra strictness
    # (slower, and a flaky single replay can drop an otherwise-good test).
    determinism_runs: int = 0

    # Run Kane on the LambdaTest cloud grid (ws-endpoint + LT:Options) instead of
    # local headless. Needs LT creds; gives video/console/network + a session URL
    # on the dashboard — the evidence needed to debug a Kane failure.
    kane_cloud: bool = False
    kane_platform: str = "Windows 10"

    # ── Execution mode ──────────────────────────────────────────────────────
    # local_execution=True  → run the pipeline in-process (local dev; default).
    # local_execution=False → the API only DISPATCHES a GitHub Actions job that
    #   runs the pipeline (P1-P8) with real resources, and streams events back to
    #   /api/runs/{id}/ingest. Keeps the hosted API tiny. See app/ci_runner.py.
    local_execution: bool = True
    runner_repo: str = ""              # "owner/repo" hosting pipeline.yml
    runner_ref: str = "main"           # branch the workflow_dispatch runs on
    runner_workflow: str = "pipeline.yml"
    public_base_url: str = ""          # this API's public URL — the CI callback target
    ingest_secret: str = ""            # shared secret authorizing CI → /ingest + /control


@lru_cache
def get_settings() -> Settings:
    return Settings()
