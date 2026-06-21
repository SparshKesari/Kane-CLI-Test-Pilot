from __future__ import annotations

import asyncio
import re
import time

from .config import get_settings
from .events import bus
from .models import ExistingTest, Phase, PhaseState, Run, RunStatus, TestArtifact


# --------------------------------------------------------------------------- #
# Public-PR naming — committed artifacts follow community conventions, not our
# internal run ids / product names. Tests get descriptive snake_case names from
# their scenario title; the branch/PR title follow Conventional Commits.
# --------------------------------------------------------------------------- #
def _slug(text: str, maxlen: int = 48) -> str:
    """snake_case identifier from a title — for test files & directories."""
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:maxlen].rstrip("_") or "scenario"


def _conventional_title(run: Run) -> str:
    """Conventional Commits PR title/commit summarising the verified areas."""
    feats = [f["feature"].lower().replace("_", " ")
             for f in run.metrics.get("feature_coverage", []) if f.get("verified", 0) > 0]
    area = ", ".join(dict.fromkeys(feats))[:60].rstrip(", ") if feats else "the application"
    return f"test: add end-to-end UI tests for {area}"

# Demo fixtures — domain-neutral; they exist only to make the agent⇄Kane loop
# visibly self-correct in DEMO_MODE without live creds. No real app is contacted
# and nothing here is app- or domain-specific.
_DEMO_EXISTING = [
    ExistingTest("tests/test_smoke.py", "test_homepage_loads", "pytest", "/"),
    ExistingTest("tests/test_smoke.py", "test_nav_renders", "pytest", "/"),
]
_DEMO_SCENARIO = {
    "id": "SC-001",
    "title": "User can open the primary navigation item and see its page",
    "expected": "The target page loads and its main heading is visible",
    # Tight objective: a precise start + a single crisp action so the Kane agent
    # converges instead of exploring. (Loose objectives make Kane wander — P4
    # scenario generation must emit precise start points + concise actions.)
    "objective": (
        "Open the first primary navigation link and confirm the resulting page "
        "renders its main heading. Do not browse elsewhere."
    ),
}
_DEMO_CODE_BROKEN = '''@pytest.mark.scenario("SC-001")
def test_sc_001_primary_nav(page):
    page.goto(TARGET_URL)
    page.click("#main-nav-link")        # wrong id — fails
    assert page.locator("h1").inner_text() != ""
'''
_DEMO_CODE_FIXED = '''@pytest.mark.scenario("SC-001")
@pytest.mark.requirement("AC-001")
def test_sc_001_primary_nav(page):
    """SC-001: User can open the primary navigation item and see its page."""
    page.goto(TARGET_URL)
    page.wait_for_load_state("domcontentloaded")
    link = page.locator("nav a").first
    link.wait_for(timeout=15000)
    link.click()
    page.wait_for_load_state("domcontentloaded")
    assert page.locator("h1").first.inner_text().strip() != ""
'''


async def _emit(run: Run, type_: str, **payload):
    await bus.publish(run.id, type_, **payload)


def _friendly_error(exc: Exception) -> str:
    """Turn a raw exception (e.g. an Anthropic 400 JSON blob) into a clear,
    actionable one-line message for the UI."""
    msg = str(exc)
    low = msg.lower()
    # ── Anthropic / LLM ────────────────────────────────────────────────────
    if "credit balance is too low" in low or "plans & billing" in low:
        return ("Anthropic API credit balance is too low. Add credits in the "
                "Anthropic Console (Plans & Billing), then start the run again.")
    if "invalid x-api-key" in low or "authentication_error" in low or "permission_error" in low:
        return "Anthropic API key is missing or invalid — check the ANTHROPIC_API_KEY setting."
    if "rate_limit" in low or "rate limit" in low or "429" in low or "overloaded" in low:
        return "Anthropic API is rate-limited or overloaded right now — wait a moment and retry."
    # ── GitHub / git ───────────────────────────────────────────────────────
    if "could not resolve to a repository" in low or "repository not found" in low:
        return "GitHub repository not found — check the repo URL and that the token can access it."
    if "clone" in low and ("failed" in low or "timed out" in low):
        return "Couldn't clone the repository — check the URL and that it's accessible."
    if "push" in low and ("denied" in low or "403" in low or "authentication" in low or "non-zero" in low):
        return "Couldn't push to the fork — the GitHub token needs `repo` + `workflow` scope."
    # ── Network ────────────────────────────────────────────────────────────
    if "timed out" in low or "timeout" in low or "connection" in low or "getaddrinfo" in low:
        return f"Network error reaching an external service — {msg.splitlines()[0][:140]}"
    # ── Fallback: first line, trimmed ──────────────────────────────────────
    return msg.splitlines()[0][:200] if msg else "Unexpected error."


# --------------------------------------------------------------------------- #
# Human-in-the-loop: the run pauses after the gate and waits for the user to
# pick which proposed scenarios Kane should verify. The API delivers the choice
# via submit_selection(), which wakes the awaiting run.
# --------------------------------------------------------------------------- #
_SELECT_EVENTS: dict[str, asyncio.Event] = {}
_SELECTIONS: dict[str, list[str]] = {}

# Per-run set of scenario ids the user asked to abort (skip / kill in-flight).
_ABORTED: dict[str, set[str]] = {}
# Runs the user asked to abort entirely — stop after the current phase, no PR.
_CANCELLED: set[str] = set()


def abort_scenario(run_id: str, scenario_id: str) -> bool:
    """User aborted a scenario: skip it if queued, kill its kane-cli if running."""
    from .services import kane_service
    _ABORTED.setdefault(run_id, set()).add(scenario_id)
    return kane_service.abort(f"{run_id}:{scenario_id}")


def abort_run(run_id: str) -> int:
    """Abort a whole run: cancel it, skip/kill all its scenarios, no PR."""
    from .models import RUNS
    from .services import kane_service
    _CANCELLED.add(run_id)
    run = RUNS.get(run_id)
    if run:
        _ABORTED.setdefault(run_id, set()).update(
            t.scenario_id for t in run.tests if t.status in ("pending", "verifying"))
    return kane_service.abort_run(run_id)


def abort_all_runs() -> int:
    """Abort every run that's still in progress."""
    from .models import RUNS, RunStatus
    n = 0
    for rid, r in list(RUNS.items()):
        if r.status == RunStatus.running:
            abort_run(rid); n += 1
    return n


def submit_selection(run_id: str, scenario_ids: list[str]) -> bool:
    """Called from the API when the user submits their scenario choice."""
    ev = _SELECT_EVENTS.get(run_id)
    if not ev:
        return False
    _SELECTIONS[run_id] = list(scenario_ids)
    ev.set()
    return True


async def _await_selection(run: Run, scenarios: list[dict], timeout: float = 1800) -> list[dict]:
    """Pause and let the user choose which scenarios to verify. Falls back to all
    scenarios if no choice arrives within `timeout`."""
    run.candidates = scenarios
    run.awaiting_selection = True
    ev = asyncio.Event()
    _SELECT_EVENTS[run.id] = ev
    p6 = run.phase("P6")
    p6.state, p6.detail = PhaseState.running, "Awaiting your selection…"
    await _emit(run, "phase", key="P6", state=p6.state.value, name=p6.name, detail=p6.detail)
    await _emit(run, "awaiting_selection", candidates=scenarios)
    try:
        await asyncio.wait_for(ev.wait(), timeout)
    except asyncio.TimeoutError:
        pass
    chosen = _SELECTIONS.pop(run.id, None)
    _SELECT_EVENTS.pop(run.id, None)
    run.awaiting_selection = False
    if chosen is not None:
        ids = set(chosen)
        scenarios = [sc for sc in scenarios if sc["id"] in ids]
    await _emit(run, "log", phase="P6",
                message=f"Verifying {len(scenarios)} selected scenario(s)")
    return scenarios


async def _start_phase(run: Run, key: str, detail: str = ""):
    p = run.phase(key)
    p.state, p.detail, p.started_at = PhaseState.running, detail, time.time()
    await _emit(run, "phase", key=key, state=p.state.value, name=p.name, detail=detail)


async def _end_phase(run: Run, key: str, detail: str = "", state=PhaseState.done):
    p = run.phase(key)
    p.state, p.ended_at = state, time.time()
    if detail:
        p.detail = detail
    await _emit(run, "phase", key=key, state=p.state.value, name=p.name, detail=p.detail)


class _RunAborted(Exception):
    """Raised to unwind a run the user aborted — handled as a clean stop."""


async def execute_run(run: Run) -> None:
    settings = get_settings()
    run.status = RunStatus.running
    await _emit(run, "run", status=run.status.value)
    try:
        if settings.demo_mode:
            await _run_demo(run)
        else:
            await _run_live(run)
        passed = [t for t in run.tests if t.authentic]
        run.verdict = "GREEN" if passed and all(
            t.authentic for t in run.tests if t.status not in ("discarded", "aborted")) else "YELLOW"
        run.status = RunStatus.passed
    except _RunAborted:
        run.status = RunStatus.aborted
        run.verdict = ""
        await _emit(run, "log", phase="P6", message="Run aborted by you.")
    except Exception as exc:  # noqa: BLE001
        run.status = RunStatus.error
        run.error = _friendly_error(exc)
        await _emit(run, "error", message=run.error)
    finally:
        _CANCELLED.discard(run.id)
    await _emit(run, "run", status=run.status.value, verdict=run.verdict,
                pr_url=run.pr_url)


# --------------------------------------------------------------------------- #
# DEMO path — simulated but realistic, streams every loop iteration.
# --------------------------------------------------------------------------- #
async def _run_demo(run: Run) -> None:
    run.branch = f"test/e2e-tests-{run.id.split('_')[-1]}"

    await _start_phase(run, "P1", "Forking & cloning…")
    await asyncio.sleep(1.0)
    run.fork_url = f"https://github.com/you/{run.repo_url.rstrip('/').split('/')[-1]}"
    await _end_phase(run, "P1", f"Fork ready · branch {run.branch}")

    await _start_phase(run, "P2", "Detecting framework & routes…")
    await asyncio.sleep(0.9)
    await _emit(run, "log", phase="P2", message="Detected: Python · pytest · Playwright")
    await _end_phase(run, "P2", "pytest + Playwright detected")

    await _start_phase(run, "P3", "Indexing existing tests…")
    await asyncio.sleep(0.8)
    run.existing_tests = list(_DEMO_EXISTING)
    await _emit(run, "tests", existing=[vars(t) for t in run.existing_tests])
    await _end_phase(run, "P3", f"{len(run.existing_tests)} existing tests indexed")

    await _start_phase(run, "P4", "Proposing meaningful scenarios…")
    await asyncio.sleep(0.9)
    await _emit(run, "log", phase="P4",
                message=f"Candidate {_DEMO_SCENARIO['id']}: {_DEMO_SCENARIO['title']}")
    await _end_phase(run, "P4", "3 scenarios proposed")

    await _start_phase(run, "P5", "Meaningfulness gate…")
    await asyncio.sleep(0.6)
    await _emit(run, "log", phase="P5",
                message="dropped SC-EXTRA: already covered by an existing test (sim 0.61)")
    await _end_phase(run, "P5", "2 kept · 1 dropped")

    await _start_phase(run, "P6", "Agent ⇄ Kane verification loop…")
    art = TestArtifact(scenario_id=_DEMO_SCENARIO["id"], title=_DEMO_SCENARIO["title"])
    run.tests.append(art)
    await _demo_loop(run, art)
    # Two non-authentic artifacts so the run view exercises the "Not verified"
    # section (with realistically long titles/reasons that stress the layout).
    f = TestArtifact(scenario_id="SC-002",
                     title="Submit the contact form with a long subject line and confirm a success toast appears")
    f.status, f.reason = "failed", ("behavior not verified — the flow did not complete on "
                                    "the live app after 2 attempt(s)")
    d = TestArtifact(scenario_id="SC-003", title="Footer newsletter signup accepts an email address")
    d.status, d.reason = "discarded", ("intent drift — objective involves ['submit'] but the agent "
                                       "performed ['update']: 'opened the newsletter section'")
    run.tests += [f, d]
    run.metrics = {
        "note": "Demo metrics.",
        "summary": {"existing_tests": 2, "scenarios_proposed": 3, "gate_kept": 3,
                    "gate_dropped": 1, "verified": 1, "discarded": 1, "failed": 1,
                    "new_tests_committed": 1, "verify_rate_pct": 33.3},
        "surface_coverage": {"elements_found": 8, "elements_exercised": 3, "pct": 37.5,
                             "uncovered": ["Settings", "Profile", "Search"]},
        "feature_coverage": [{"feature": "NAVIGATION", "proposed": 2, "verified": 1}],
        "criticality": {"HIGH": {"proposed": 2, "verified": 1},
                        "MEDIUM": {"proposed": 1, "verified": 0},
                        "LOW": {"proposed": 0, "verified": 0}},
        "phase_durations_s": {}, "total_duration_s": 0,
    }
    await _emit(run, "metrics", metrics=run.metrics)
    await _end_phase(run, "P6", f"{_DEMO_SCENARIO['id']} verified authentic")

    await _start_phase(run, "P7", "Kane CI workflow…")
    await asyncio.sleep(0.8)
    await _emit(run, "log", phase="P7",
                message="Kane CI workflow re-verifies the suite on every push/PR · added .github/workflows/kane-tests.yml")
    await _end_phase(run, "P7", "CI workflow committed · 1 test")

    await _start_phase(run, "P8", "Committing & opening PR…")
    await asyncio.sleep(1.0)
    run.pr_url = f"{run.repo_url.rstrip('/')}/pull/42"
    await _emit(run, "tests", generated=[vars(t) for t in run.tests])
    await _end_phase(run, "P8", "PR opened")


async def _demo_loop(run: Run, art: TestArtifact):
    sc = _DEMO_SCENARIO

    async def loop(it, phase, status, detail, **extra):
        await _emit(run, "loop", scenario=sc["id"], iteration=it,
                    step=phase, status=status, detail=detail, **extra)
        await asyncio.sleep(0.8)

    await loop(1, "kane_verify", "pass",
               "Kane drove the live app and observed the behavior",
               kane_session="https://automation.lambdatest.com/test?testID=demo-001",
               steps=["Open the home page", "Click the first nav link", "Target page heading visible"])
    art.kane_session = "https://automation.lambdatest.com/test?testID=demo-001"

    await loop(1, "synthesize", "info", "Agent synthesized a test from Kane's trace",
               code=_DEMO_CODE_BROKEN)
    art.code = _DEMO_CODE_BROKEN

    await loop(1, "execute", "fail",
               "AssertionError: locator '#main-nav-link' not found",
               error="playwright._impl._errors.TimeoutError: #main-nav-link")

    await loop(2, "repair", "info",
               "Agent repaired locators using the real DOM Kane saw",
               code=_DEMO_CODE_FIXED)
    art.code = _DEMO_CODE_FIXED
    art.repair_iterations = 1

    await loop(2, "execute", "pass", "Test passed")
    await loop(2, "determinism", "pass", "Ran 3× — stable, not flaky")
    art.status, art.authentic = "authentic", True
    await loop(2, "accept", "pass", "Accepted into the suite ✅")


def _write_suite_readme(out_dir, run: Run, want_vanilla: bool) -> None:
    from pathlib import Path
    rows = "\n".join(
        f"- `{_slug(t.title)}/` — {t.title}"
        for t in run.tests if t.authentic)
    if want_vanilla:
        how = ("Dependency-free Playwright-Python tests.\n\n"
               "```bash\npip install playwright pytest pytest-playwright\n"
               "playwright install chromium\npytest tests/e2e -v\n```")
    else:
        how = ("Each test lives in its own folder with a `requirements.txt`.\n\n"
               "**Run a test:**\n```bash\ncd tests/e2e/<test-name>\n"
               "pip install -r requirements.txt\nplaywright install chromium\n"
               "python test.py\n```")
    Path(out_dir, "README.md").write_text(
        "# End-to-end UI tests\n\n"
        "Automated end-to-end tests for this app's UI. Each test was generated from "
        "the live application and verified against it in a real browser before being "
        "committed, so every test exercises a behavior that genuinely works.\n\n"
        f"## Tests\n{rows}\n\n## How to run\n{how}\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# One scenario through the agent⇄Kane loop. Runs concurrently (bounded by the
# P6 semaphore); `art` is pre-created so run.tests order stays deterministic.
# --------------------------------------------------------------------------- #
async def _verify_scenario(run: Run, sc: dict, art: TestArtifact, out_dir,
                           local, want_vanilla: bool,
                           test_vars: dict | None = None, test_ctx: str = "") -> None:
    import shutil
    from pathlib import Path
    from .services import agent_service, executor, gate_service, kane_service

    settings = get_settings()
    name = _slug(sc["title"])              # descriptive snake_case for files/dirs
    # kane-cli --name allows only [A-Za-z0-9_-] (no spaces) — use the slug, not
    # the raw title, or every Kane run fails with an "invalid name" error.
    abort_key = f"{run.id}:{sc['id']}"
    aborted = lambda: sc["id"] in _ABORTED.get(run.id, set()) or run.id in _CANCELLED
    if aborted():                          # aborted while still queued — skip it
        art.status, art.reason = "aborted", "Aborted by you before it started"
        await _emit(run, "tests")
        return
    art.status = "verifying"               # in-flight — shows live in the checklist
    await _emit(run, "tests")
    try:
        # Kane's agent is nondeterministic — retry a non-converging run a few times
        # before giving up, so flakiness doesn't discard a genuinely testable flow.
        attempts = max(1, settings.kane_attempts)
        for attempt in range(1, attempts + 1):
            kr = await asyncio.to_thread(
                kane_service.verify, sc["objective"], run.target_url, name, local, abort_key,
                test_vars or {}, test_ctx)
            if kr.ok or attempt == attempts or aborted():
                break
            await _emit(run, "loop", scenario=sc["id"], iteration=attempt, step="kane_verify",
                        status="info",
                        detail=f"Kane attempt {attempt}/{attempts} did not converge — retrying")
        if aborted():                       # killed mid-run by the user
            art.status, art.reason = "aborted", "Aborted by you"
            await _emit(run, "loop", scenario=sc["id"], iteration=1, step="abort",
                        status="info", detail="Aborted by you")
            return
        # Attach the Kane session to the artifact for EVERY outcome (pass, fail,
        # discard) — so the UI can link to the session even when it didn't pass.
        art.kane_session = kr.session_id
        art.kane_test_url = kr.test_url
        await _emit(run, "loop", scenario=sc["id"], iteration=1, step="kane_verify",
                    status="pass" if kr.ok else "fail", detail=kr.one_liner,
                    kane_session=kr.session_id, kane_test_url=kr.test_url, steps=kr.steps)
        if not kr.ok:
            # FAILED, not discarded: we tried to verify the behavior on the live
            # app and it did not complete (broken feature, error, or hang). That's
            # a real signal worth surfacing — not a quiet quality-drop.
            art.status, art.reason = "failed", \
                f"behavior not verified — the flow did not complete on the live app " \
                f"after {attempts} attempt(s)"
            return
        # Intent gate: Kane passing (exit 0) is not enough — it must have done the
        # action the scenario was ABOUT, not wandered off and succeeded at
        # something else. Drop "false greens" before they ever become a test.
        ok_intent, intent_reason = gate_service.intent_match(
            sc["objective"], kr.one_liner, kr.steps)
        if not ok_intent:
            art.status, art.reason = "discarded", intent_reason
            await _emit(run, "loop", scenario=sc["id"], iteration=1, step="intent_gate",
                        status="fail", detail=intent_reason)
            return

        export = await asyncio.to_thread(kane_service.read_export, kr.code_dir)
        if want_vanilla:
            # Prefer Kane's own deterministic `testmd export` (standalone
            # Playwright, no LLM drift); fall back to the LLM translation, then to
            # the raw testmu-dialect export.
            code = await asyncio.to_thread(kane_service.export_vanilla, kr.test_md, local)
            if code:
                detail = "Kane `testmd export` produced standalone Playwright"
            elif export:
                code = await asyncio.to_thread(
                    agent_service.synthesize, sc["objective"], sc["expected"],
                    kr.steps, export)
                detail = "Agent translated Kane's trace to vanilla Playwright"
            else:
                code = "# Kane produced no exportable code"
                detail = "No Kane export available"
        else:
            code = export or "# Kane produced no exportable code"
            detail = "Committing Kane's testmu-dialect Playwright-Python export as-is"
        art.code = code
        await _emit(run, "loop", scenario=sc["id"], iteration=1, step="synthesize",
                    status="info", detail=detail, code=code[:2000])

        # Assertion gate: lint the ACTUAL committed body. A test that only asserts
        # page-load/tautologies (count()>=0, title present) would go green even if
        # the feature were broken — reject it rather than ship false confidence.
        ok_assert, assert_reason = await asyncio.to_thread(gate_service.assert_quality, code)
        if not ok_assert:
            art.status, art.reason = "discarded", assert_reason
            await _emit(run, "loop", scenario=sc["id"], iteration=1, step="assert_gate",
                        status="fail", detail=assert_reason)
            return

        # Optional strictness: replay Kane's saved test (off by default — Kane's
        # live verify is the authenticity proof; replays are slow and can be flaky).
        if kr.test_md and Path(kr.test_md).exists() and settings.determinism_runs > 0:
            stable, results = await asyncio.to_thread(
                executor.determinism, Path(kr.test_md), settings.determinism_runs)
            await _emit(run, "loop", scenario=sc["id"], iteration=2, step="determinism",
                        status="pass" if stable else "fail",
                        detail=f"Replayed {len(results)}× — {'stable' if stable else 'flaky'}")
            art.authentic = stable
            art.status = "authentic" if stable else "failed"
        else:
            art.authentic, art.status = True, "authentic"  # Kane pass is the evidence

        if art.authentic:
            await _emit(run, "loop", scenario=sc["id"], iteration=2, step="accept",
                        status="pass", detail="Accepted into the suite ✅")
            dest = out_dir / name                  # tests/e2e/<descriptive_name>/
            dest.mkdir(parents=True, exist_ok=True)
            if want_vanilla:
                (dest / f"test_{name}.py").write_text(code, encoding="utf-8")
            elif kr.code_dir and Path(kr.code_dir).exists():
                shutil.copytree(kr.code_dir, dest, dirs_exist_ok=True)
            else:
                (dest / "test.py").write_text(code, encoding="utf-8")
            if kr.test_md and Path(kr.test_md).exists():
                (dest / f"{name}.md").write_text(
                    Path(kr.test_md).read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:  # noqa: BLE001 — one scenario must not crash the run
        art.status, art.reason = "failed", f"error: {exc}"[:200]
        await _emit(run, "loop", scenario=sc["id"], iteration=1, step="execute",
                    status="fail", detail=f"error: {str(exc)[:140]}")


# --------------------------------------------------------------------------- #
# LIVE path — real fork/clone + Kane verify + replay + commit/PR.
# The LLM agent (synthesize/repair) activates automatically when an Anthropic
# key is present; otherwise Kane's own export is committed as the test.
# --------------------------------------------------------------------------- #
async def _run_live(run: Run) -> None:
    import shutil
    from pathlib import Path
    from .services import (agent_service, code_intel, crawl_service, executor,
                           gate_service, github_service, kane_ci,
                           kane_service, metrics_service, repo_intel, scenario_service)

    settings = get_settings()
    want_vanilla = settings.test_style == "vanilla" and bool(settings.anthropic_api_key)
    run.branch = f"test/e2e-tests-{run.id.split('_')[-1]}"

    await _start_phase(run, "P1", "Forking & cloning…")
    fork_url, local = await asyncio.to_thread(
        github_service.fork_and_clone, run.repo_url, run.branch)
    run.fork_url = fork_url
    fork_slug = fork_url.replace("https://github.com/", "")
    await _end_phase(run, "P1", f"Fork ready · {run.branch}")

    await _start_phase(run, "P2", "Repo intelligence…")
    prof = await asyncio.to_thread(repo_intel.profile, local)
    await _emit(run, "log", phase="P2", message=f"Detected: {', '.join(prof['frameworks'])}")
    # Read the app's own page/flow source so P4 can ground scenarios in real
    # routes, exact rendered strings, and conditional/empty/error states — not
    # just the rendered homepage snapshot.
    code_map = await asyncio.to_thread(code_intel.collect, local)
    if code_map.get("files_read"):
        rts = ", ".join(code_map.get("routes", [])[:8]) or "—"
        await _emit(run, "log", phase="P2",
                    message=f"Read {code_map['files_read']} source files · routes: {rts}")
    await _end_phase(run, "P2",
                     f"{' · '.join(prof['frameworks'])} · {code_map.get('files_read', 0)} src files")

    await _start_phase(run, "P3", "Existing-test inventory…")
    run.existing_tests = await asyncio.to_thread(repo_intel.inventory, local)
    await _emit(run, "tests", existing=[vars(t) for t in run.existing_tests])
    await _end_phase(run, "P3", f"{len(run.existing_tests)} existing tests indexed")

    await _start_phase(run, "P4", "Understanding the app & proposing scenarios…")
    crawl = await asyncio.to_thread(crawl_service.crawl, run.target_url)
    await _emit(run, "log", phase="P4",
                message=(f"Crawled live UI · {len(crawl.get('links', []))} links, "
                         f"{len(crawl.get('forms', []))} forms"))
    # Mode: greenfield (few/no existing tests → broad coverage) vs gap-fill
    # (existing tests → only the missing cases). A per-run max_scenarios > 0 is a
    # hard override; otherwise the budget is chosen by mode.
    greenfield = len(run.existing_tests) <= settings.greenfield_max_existing
    covered = gate_service.coverage_of(run.existing_tests)
    budget = run.max_scenarios if run.max_scenarios > 0 else (
        settings.scenario_budget_greenfield if greenfield
        else settings.scenario_budget_gapfill)
    mode_label = ("greenfield — broad coverage" if greenfield
                  else f"gap-fill — covers {', '.join(covered) or 'unknown areas'}")
    await _emit(run, "log", phase="P4", message=f"Mode: {mode_label} · budget {budget}")
    scenarios = await asyncio.to_thread(
        scenario_service.propose, prof, run.existing_tests, crawl, run.target_url,
        mode="greenfield" if greenfield else "gapfill",
        budget=budget, covered_features=covered, code_map=code_map)
    for sc in scenarios:
        await _emit(run, "log", phase="P4",
                    message=f"{sc['id']} [{sc['criticality']}/{sc.get('scenario_type','HAPPY')}] {sc['title']}")
    if not scenarios:
        # Do NOT fabricate a scenario here — a canned/placeholder flow injected
        # into an unrelated app produces a test Kane can't perform (false work).
        # End gracefully instead; the metrics + empty P6 make the cause visible.
        await _emit(run, "log", phase="P4",
                    message="No scenarios generated from the live UI — nothing to verify.")
    proposed = list(scenarios)        # snapshot for the metrics report
    await _end_phase(run, "P4", f"{len(scenarios)} scenario(s) proposed")

    await _start_phase(run, "P5", "Meaningfulness gate…")
    kept, dropped = await asyncio.to_thread(
        gate_service.filter_scenarios, scenarios, run.existing_tests, crawl)
    for d in dropped:
        await _emit(run, "log", phase="P5",
                    message=f"dropped {d.get('id','?')}: {d['drop_reason']}")
    scenarios = kept or scenarios
    await _end_phase(run, "P5", f"{len(kept)} kept · {len(dropped)} dropped")

    # Human-in-the-loop: pause and let the user pick which scenarios to verify.
    if run.mode == "human" and scenarios:
        scenarios = await _await_selection(run, scenarios)

    await _start_phase(run, "P6", "Agent ⇄ Kane loop…")
    out_dir = local / "tests" / "e2e"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Generate run-unique throwaway test data ONCE (so every scenario shares the
    # same identity), then hand it to Kane as variables + a context file so it can
    # fill forms and get past sign-in walls instead of dead-ending at auth.
    test_vars: dict = {}
    test_ctx = ""
    if settings.test_data_enabled:
        data = await asyncio.to_thread(
            agent_service.generate_test_data, prof, crawl, run.target_url)
        test_vars = kane_service.build_variables(data)
        test_ctx = kane_service.build_context(data)
        await _emit(run, "log", phase="P6",
                    message=f"Test identity ready ({data.get('email','')}) — "
                            "Kane will sign in / fill forms with it where needed")
    # Pre-create artifacts in scenario order so the committed suite + PR list are
    # deterministic even though the Kane verifications run concurrently. Each
    # scenario is one live Kane run; a bounded semaphore caps how many hit the
    # grid at once (KANE_CONCURRENCY).
    arts = [TestArtifact(scenario_id=sc["id"], title=sc["title"]) for sc in scenarios]
    run.tests.extend(arts)
    await _emit(run, "tests")          # show the full scenario checklist immediately (all queued)
    sem = asyncio.Semaphore(max(1, settings.kane_concurrency))
    total, done = len(scenarios), 0

    async def _guarded(sc: dict, art: TestArtifact):
        nonlocal done
        async with sem:
            await _verify_scenario(run, sc, art, out_dir, local, want_vanilla,
                                   test_vars, test_ctx)
        done += 1
        p = run.phase("P6")
        p.detail = f"{done}/{total} scenarios verified · {sum(t.authentic for t in run.tests)} passed"
        await _emit(run, "phase", key="P6", state=p.state.value, name=p.name, detail=p.detail)
        await _emit(run, "tests")      # refresh the checklist as each scenario settles

    await asyncio.gather(*[_guarded(sc, art) for sc, art in zip(scenarios, arts)])

    # Whole-run abort: stop here — no suite, no CI, no PR.
    if run.id in _CANCELLED:
        await _end_phase(run, "P6", "aborted by you", state=PhaseState.failed)
        for k in ("P7", "P8"):
            await _end_phase(run, k, "skipped — run aborted", state=PhaseState.skipped)
        await _emit(run, "tests")
        raise _RunAborted()

    _write_suite_readme(out_dir, run, want_vanilla)
    run.metrics = metrics_service.build(run, crawl, proposed, dropped)
    (out_dir / "COVERAGE.md").write_text(
        metrics_service.to_markdown(run.metrics, run), encoding="utf-8")
    await _emit(run, "metrics", metrics=run.metrics)
    await _end_phase(run, "P6", f"{sum(t.authentic for t in run.tests)} verified authentic")

    # P7 · Kane CI workflow. Commit a GitHub Actions workflow that re-verifies the
    # committed Kane tests in a real browser via Kane CLI on every push/PR — the
    # same tool that verified them. No separate runner, no vanilla translation.
    await _start_phase(run, "P7", "Kane CI workflow…")
    authentic = [t for t in run.tests if t.authentic]
    ci_paths: list[str] = []
    if authentic:
        ci = await asyncio.to_thread(kane_ci.generate_ci_workflow, local)
        ci_paths = [ci["added"]]
        ci_note = ("added a GitHub Actions pipeline (the repo had no CI)"
                   if not ci["existing_ci"]
                   else f"added a Kane CI workflow alongside existing CI ({', '.join(ci['existing_ci'])})")
        await _emit(run, "log", phase="P7",
                    message=f"Kane CI workflow re-verifies {len(authentic)} test(s) on every push/PR · {ci_note}")
        await _end_phase(run, "P7", f"CI workflow committed · {len(authentic)} tests")
    else:
        await _end_phase(run, "P7", "skipped — no authentic tests", state=PhaseState.skipped)

    await _start_phase(run, "P8", "Commit & open PR…")
    # Don't open a PR with nothing verified — that's how junk/empty PRs (and the
    # "commit nothing" git error) happen. Only commit when there's a real test.
    authentic_tests = [t for t in run.tests if t.authentic]
    if not authentic_tests:
        await _end_phase(run, "P8", "skipped — no verified tests to commit",
                         state=PhaseState.skipped)
    else:
        ci_line = ""
        if ci_paths:
            ci_line = ("\n\n**CI included** — a GitHub Actions workflow "
                       "(`.github/workflows/kane-tests.yml`) that re-verifies these tests in a real "
                       "browser via [Kane CLI](https://www.testmuai.com/kane-cli/) on every push/PR. "
                       "Add repo secrets `LT_USERNAME` / `LT_ACCESS_KEY` to enable it.")
        sc = run.metrics.get("surface_coverage", {})
        cov_line = (f"\n\n**Coverage:** {len(authentic_tests)} tests · "
                    f"{sc.get('pct', 0)}% of the discovered UI surface — see `tests/e2e/COVERAGE.md`.")
        def _pr_line(t: TestArtifact) -> str:
            mark = "✅" if t.authentic else ("❌" if t.status == "failed" else "⚠️")
            line = f"- {mark} {t.title} (**{'verified' if t.authentic else t.status}**)"
            if t.kane_test_url:
                line += f" — [session]({t.kane_test_url})"
            if not t.authentic and t.reason:        # surface WHY it didn't make it
                line += f"\n    └ _{t.reason[:160]}_"
            return line
        verified = [t for t in run.tests if t.authentic]
        not_ver = [t for t in run.tests if not t.authentic]
        body = ("## End-to-end UI tests\n\n"
                "Automated end-to-end tests generated from the live application. Each was "
                "**verified against the running app in a real browser** before being committed, "
                f"so every test exercises a behavior that genuinely works — **{len(verified)} verified**"
                + (f", {len(not_ver)} not verified (listed below for transparency)" if not_ver else "")
                + ".\n\n### Verified (committed)\n"
                + ("\n".join(_pr_line(t) for t in verified) or "_none_"))
        if not_ver:
            body += ("\n\n### Not verified (not committed — shown for transparency)\n"
                     + "\n".join(_pr_line(t) for t in not_ver))
        body += cov_line + ci_line
        pr = await asyncio.to_thread(
            github_service.commit_and_pr, local, run.branch, fork_slug,
            _conventional_title(run), body, True, extra_paths=ci_paths)
        run.pr_url = pr
        await _end_phase(run, "P8", "PR opened")
