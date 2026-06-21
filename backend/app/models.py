from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class RunStatus(str, Enum):
    queued = "queued"
    running = "running"
    passed = "passed"
    failed = "failed"
    error = "error"
    aborted = "aborted"


class PhaseState(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    skipped = "skipped"
    failed = "failed"


PHASES: list[tuple[str, str]] = [
    ("P1", "Fork & clone"),
    ("P2", "Repo intelligence"),
    ("P3", "Existing-test inventory"),
    ("P4", "Candidate scenarios"),
    ("P5", "Meaningfulness gate"),
    ("P6", "Agent ⇄ Kane loop"),
    ("P7", "Kane CI workflow"),
    ("P8", "Commit & open PR"),
]


@dataclass
class Phase:
    key: str
    name: str
    state: PhaseState = PhaseState.pending
    detail: str = ""
    started_at: Optional[float] = None
    ended_at: Optional[float] = None


@dataclass
class TestArtifact:
    scenario_id: str
    title: str
    framework: str = "playwright-python"
    code: str = ""
    status: str = "pending"        # pending | authentic | failed | discarded
    authentic: bool = False
    repair_iterations: int = 0
    kane_session: str = ""
    kane_test_url: str = ""        # LambdaTest session URL (cloud grid runs)
    reason: str = ""


@dataclass
class ExistingTest:
    file: str
    name: str
    framework: str
    target: str = ""


@dataclass
class Run:
    repo_url: str
    target_url: str
    id: str = field(default_factory=lambda: _id("run"))
    max_scenarios: int = 0   # 0 = auto (budget chosen by greenfield/gap-fill mode)
    mode: str = "auto"       # "auto" | "human" (human-in-the-loop scenario selection)
    awaiting_selection: bool = False    # paused, waiting for the user to pick scenarios
    candidates: list = field(default_factory=list)   # proposed scenarios shown for selection
    status: RunStatus = RunStatus.queued
    verdict: str = ""
    error: str = ""          # human-readable failure message when status == error
    fork_url: str = ""
    branch: str = ""
    pr_url: str = ""
    created_at: float = field(default_factory=time.time)
    phases: list[Phase] = field(default_factory=lambda: [Phase(k, n) for k, n in PHASES])
    existing_tests: list[ExistingTest] = field(default_factory=list)
    tests: list[TestArtifact] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def phase(self, key: str) -> Phase:
        return next(p for p in self.phases if p.key == key)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "repo_url": self.repo_url,
            "target_url": self.target_url,
            "max_scenarios": self.max_scenarios,
            "mode": self.mode,
            "awaiting_selection": self.awaiting_selection,
            "candidates": self.candidates,
            "status": self.status.value,
            "verdict": self.verdict,
            "error": self.error,
            "fork_url": self.fork_url,
            "branch": self.branch,
            "pr_url": self.pr_url,
            "created_at": self.created_at,
            "phases": [
                {
                    "key": p.key,
                    "name": p.name,
                    "state": p.state.value,
                    "detail": p.detail,
                    "started_at": p.started_at,
                    "ended_at": p.ended_at,
                }
                for p in self.phases
            ],
            "existing_tests": [vars(t) for t in self.existing_tests],
            "tests": [vars(t) for t in self.tests],
            "metrics": self.metrics,
        }


# In-memory store (MVP). Swap for Postgres in v1.
RUNS: dict[str, Run] = {}
