from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecResult:
    ok: bool
    output: str


def replay(test_md: Path, timeout: int = 180) -> ExecResult:
    """Re-run a Kane-saved *_test.md via kane-cli (uses kane's own OAuth).

    This is the authenticity / determinism check: replaying the exact saved
    test proves the behavior is still observable and the test is stable.
    """
    from .kane_service import auth_flags
    proc = subprocess.run(
        ["kane-cli", "testmd", "run", str(test_md), "--agent", "--headless", *auth_flags()],
        capture_output=True, text=True, timeout=timeout,
    )
    return ExecResult(ok=proc.returncode == 0, output=(proc.stdout + proc.stderr)[-4000:])


def determinism(test_md: Path, runs: int = 1) -> tuple[bool, list[ExecResult]]:
    """Run the replay N times; stable iff every run passes. runs<=0 skips the
    check entirely (trusts Kane's verify), which avoids extra cloud runs."""
    if runs <= 0:
        return True, []
    results = [replay(test_md) for _ in range(runs)]
    return all(r.ok for r in results), results
