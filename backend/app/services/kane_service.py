from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from ..config import get_settings


def build_variables(data: dict) -> dict:
    """Kane --variables payload ({{key}} → value) from a generated test-data dict.
    Empty dict → no variables passed."""
    if not data:
        return {}
    return {
        "email":    {"value": data.get("email", ""),    "secret": False},
        "password": {"value": data.get("password", ""), "secret": True},
        "name":     {"value": data.get("name", ""),     "secret": False},
        "url":      {"value": data.get("url", ""),       "secret": False},
    }


def build_context(data: dict) -> str:
    """Agent --local-context markdown from a generated test-data dict — tells the
    agent how to use the data and, crucially, how to get PAST a sign-in wall."""
    if not data:
        return ""
    return (
        "# Automated QA test context\n\n"
        "You are testing this app with disposable QA test data generated for this "
        "run. Use it freely; never use real personal data.\n\n"
        "## Test data (also available as variables: {{email}}, {{password}}, {{name}}, {{url}})\n"
        f"- Email: {data.get('email', '')}\n"
        f"- Password: {data.get('password', '')}\n"
        f"- Name / username: {data.get('name', '')}\n"
        f"- A URL for any URL/link field: {data.get('url', '')}\n\n"
        "## Getting past a sign-in wall\n"
        "If an action or page requires being signed in:\n"
        "1. If a sign-up / register option exists, create an account with the email "
        "and password above (and the name if asked), then continue the task.\n"
        "2. Otherwise log in with the email and password above.\n"
        "Treat this data as valid; fill required fields with realistic values "
        "instead of leaving them blank.\n"
    )

KANE_SESSIONS_DIR = Path.home() / ".testmuai" / "kaneai" / "sessions"
_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def auth_flags() -> list[str]:
    """Basic-auth flags (skip OAuth) when LT creds are configured — used by both
    `kane-cli run` and `kane-cli testmd run`. Falls back to the logged-in
    profile when creds are unset."""
    s = get_settings()
    if s.lt_username and s.lt_access_key:
        return ["--username", s.lt_username, "--access-key", s.lt_access_key]
    return []


@dataclass
class KaneResult:
    ok: bool
    one_liner: str
    steps: list[str]
    session_id: str
    test_md: str = ""        # replayable *_test.md path
    code_dir: str = ""       # dir containing exported playwright-python test.py
    raw_tail: str = ""
    status: str = ""         # run_end.status when available ("passed"/"failed"/…)
    summary: str = ""        # run_end.summary — Kane's prose verdict
    duration: float | None = None
    test_url: str = ""       # LambdaTest session URL (cloud grid runs only)
    extra: dict = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Code-export resolution — Kane prints the export dir in several shapes
# (NDJSON code_export event, a plaintext "CodeExport file://…" links box, or a
# bare session path). We try all of them, then fall back to the deterministic
# sessions/<id>/code-export path.
# --------------------------------------------------------------------------- #
def _parse_file_url(raw: str) -> str:
    """Convert a file:// URL (from Kane's CodeExport link) to an OS path,
    handling Linux (file:///home/…) and Windows (file:///C:/…) forms."""
    token = raw.strip()
    if not token.lower().startswith("file://"):
        return token
    no_scheme = token[7:]
    if sys.platform == "win32" and no_scheme.startswith("/") \
            and len(no_scheme) > 2 and no_scheme[2] == ":":
        no_scheme = no_scheme[1:]
    return no_scheme


def _resolve_export_dir(raw_path: str) -> str:
    """Return the directory holding the exported *.py — the path itself or its
    parent — only if it actually contains Python files."""
    p = Path(raw_path)
    for cand in (p, p.parent):
        if cand.is_dir() and any(cand.glob("*.py")):
            return str(cand)
    return ""


def _export_by_session(session_id: str) -> str:
    if not session_id:
        return ""
    cand = KANE_SESSIONS_DIR / session_id / "code-export"
    return str(cand) if cand.is_dir() and any(cand.glob("*.py")) else ""


def _cloud_ws_endpoint(username: str, access_key: str, name: str) -> str:
    """Build a LambdaTest Playwright-grid ws-endpoint with full LT:Options so the
    Kane session lands on the dashboard with video/console/network artifacts and
    a real session URL — the evidence you need to debug a Kane failure."""
    s = get_settings()
    pw_version = ""
    try:
        r = subprocess.run(["playwright", "--version"],
                           capture_output=True, text=True, check=False)
        parts = r.stdout.strip().split()
        pw_version = parts[1] if len(parts) >= 2 else ""
    except Exception:  # noqa: BLE001
        pass
    caps = {
        "browserName": "Chrome",
        "browserVersion": "latest",
        "LT:Options": {
            "platform": s.kane_platform,
            "name": name,
            "user": username,
            "accessKey": access_key,
            "network": True, "video": True, "console": True,
            "tunnel": False, "tunnelName": "",
            "playwrightClientVersion": pw_version,
        },
    }
    return ("wss://cdp.lambdatest.com/playwright?capabilities="
            + urllib.parse.quote(json.dumps(caps)))


# Live kane-cli processes, keyed so the API can abort a specific scenario.
_RUNNING: dict[str, subprocess.Popen] = {}


def _kill_tree(p: subprocess.Popen) -> None:
    """Kill kane-cli AND the headless Chrome it spawned — they share a process
    group (start_new_session). Killing only kane-cli orphans Chrome, which holds
    a CDP port (9222-9230) and eventually exhausts them so every run fails."""
    import os
    import signal
    try:
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            p.terminate()
        except Exception:  # noqa: BLE001
            pass


def abort(key: str) -> bool:
    """Kill the in-flight kane-cli (and its Chrome) for `key`."""
    p = _RUNNING.get(key)
    if p and p.poll() is None:
        _kill_tree(p)
        return True
    return False


def abort_run(run_id: str) -> int:
    """Kill every in-flight kane-cli (and its Chrome) belonging to a run."""
    n = 0
    for key, p in list(_RUNNING.items()):
        if key.startswith(f"{run_id}:") and p and p.poll() is None:
            _kill_tree(p); n += 1
    return n


def verify(objective: str, target_url: str, name: str, cwd: Path,
           abort_key: str | None = None,
           variables: dict | None = None, context: str | None = None) -> KaneResult:
    """Drive the live app with Kane to prove the behavior is real, and capture
    the replayable test + exported code. Runs headless locally by default, or on
    the LambdaTest cloud grid when KANE_CLOUD=true and creds are set. Registered
    under `abort_key` so it can be killed mid-run via abort().

    `variables` ({{key}} → value, kane --variables) and `context` (markdown agent
    instructions, kane --local-context) let the agent fill forms and get past
    sign-in walls with throwaway test data."""
    s = get_settings()
    # kane-cli --name accepts only [A-Za-z0-9_-]; sanitize so a spaced/odd name
    # can never make the whole run fail with "invalid name".
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")[:60] or "scenario"
    cmd = ["kane-cli", "run", objective, "--url", target_url,
           "--agent", "--headless", "--timeout", "120", "--max-steps", "15",
           "--code-export", "--code-language", "python", "--skip-code-validation",
           "--name", name, *auth_flags()]
    if variables:
        cmd += ["--variables", json.dumps(variables)]
    ctx_path = ""
    if context:
        fd, ctx_path = tempfile.mkstemp(suffix=".md", prefix="kane-ctx-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(context)
        cmd += ["--local-context", ctx_path]
    if s.kane_cloud and s.lt_username and s.lt_access_key:
        cmd += ["--ws-endpoint",
                _cloud_ws_endpoint(s.lt_username, s.lt_access_key, name)]

    # start_new_session=True puts kane-cli + its Chrome in one process group so
    # _kill_tree can reap both (no orphaned Chrome holding a CDP port).
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, cwd=str(cwd), encoding="utf-8", errors="replace",
                            start_new_session=True)
    if abort_key:
        _RUNNING[abort_key] = proc
    try:
        out, err = proc.communicate(timeout=s.kane_timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        out, err = proc.communicate()
    finally:
        if abort_key:
            _RUNNING.pop(abort_key, None)
        if ctx_path:
            try: os.unlink(ctx_path)
            except OSError: pass
    combined = (out or "") + "\n" + (err or "")

    steps: list[str] = []
    session_id = test_md = output_path = code_dir = ""
    run_end: dict | None = None

    for raw in combined.splitlines():
        line = raw.strip()
        if not line:
            continue
        # ── NDJSON events ──────────────────────────────────────────────────
        if line.startswith("{"):
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                ev = None
            if ev is not None:
                etype = ev.get("type", "")
                if etype == "recording_state":
                    session_id = ev.get("session_id", session_id)
                    test_md = ev.get("test_path", test_md)
                    output_path = ev.get("output_path", output_path)
                elif etype in ("step_end", "stepEnd") and ev.get("summary"):
                    steps.append(ev["summary"])
                elif etype in ("run_end", "runEnd"):
                    run_end = ev
                    session_id = (ev.get("session_id") or ev.get("sessionId")
                                  or ev.get("data", {}).get("session_id", "")
                                  or session_id)
                elif etype in ("code_export", "codeExport"):
                    rp = ev.get("path") or ev.get("directory") or ""
                    if rp:
                        code_dir = _resolve_export_dir(_parse_file_url(rp)) or code_dir
                # legacy per-step "done" remarks (older CLI without step_end)
                if ev.get("status") == "done" and ev.get("remark"):
                    r = ev["remark"]
                    if not r.startswith("Step "):
                        steps.append(r)
                if not session_id:
                    session_id = ev.get("session_id") or ev.get("sessionId") or ""
                continue
        # ── Plaintext "CodeExport file://…" links box ──────────────────────
        if not code_dir and "CODEEXPORT" in line.upper().replace(" ", "").replace("-", ""):
            for tok in line.split():
                if tok.lower().startswith("file://"):
                    code_dir = _resolve_export_dir(_parse_file_url(tok)) or code_dir
                elif "code-export" in tok.lower() or "kaneai/sessions" in tok.lower():
                    code_dir = _resolve_export_dir(tok) or code_dir
                if code_dir:
                    break
        if not session_id and "sessions" in line.lower():
            m = _UUID_RE.search(line)
            if m:
                session_id = m.group(0)

    # ── Resolve export dir: explicit hits → output_path → session-id path ──
    if not code_dir and output_path:
        code_dir = _resolve_export_dir(str(Path(output_path) / "playwright-python-code")) \
            or _resolve_export_dir(output_path)
    if not code_dir:
        code_dir = _export_by_session(session_id)

    # ── Verdict: prefer run_end.status, fall back to process exit code ─────
    if run_end is not None:
        status = run_end.get("status", "")
        ok = status == "passed" if status else (proc.returncode == 0)
        summary = run_end.get("summary", "")
        one_liner = run_end.get("one_liner", "") or (steps[-1] if steps else "")
        duration = run_end.get("duration")
        test_url = run_end.get("test_url", "")
    else:
        ok = proc.returncode == 0
        status = "passed" if ok else "failed"
        summary = ""
        one_liner = steps[-1] if steps else (objective if ok else "no observable result")
        duration = None
        test_url = ""

    return KaneResult(
        ok=ok, one_liner=one_liner, steps=steps, session_id=session_id,
        test_md=test_md, code_dir=code_dir, status=status, summary=summary,
        duration=duration, test_url=test_url,
        raw_tail=combined[-2000:],
    )


def read_export(code_dir: str) -> str:
    p = Path(code_dir) / "test.py"
    return p.read_text(encoding="utf-8", errors="ignore") if p.exists() else ""


def export_vanilla(test_md: str, cwd: Path) -> str:
    """Ask Kane for standalone (dependency-free) Playwright code via
    `kane-cli testmd export`. Returns "" on any failure so callers can fall
    back to the LLM translation or the raw testmu-dialect export."""
    if not test_md or not Path(test_md).exists():
        return ""
    try:
        proc = subprocess.run(
            ["kane-cli", "testmd", "export", test_md,
             "--code-language", "python", *auth_flags()],
            capture_output=True, text=True, timeout=120, cwd=str(cwd),
            encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""
    if proc.returncode != 0:
        return ""
    # Kane may print the code to stdout, or write a file and print its path.
    out = proc.stdout
    for line in out.splitlines():
        tok = line.strip()
        if tok.lower().endswith(".py") and Path(_parse_file_url(tok)).exists():
            return Path(_parse_file_url(tok)).read_text(encoding="utf-8", errors="ignore")
    return out if "def test" in out or "page." in out else ""
