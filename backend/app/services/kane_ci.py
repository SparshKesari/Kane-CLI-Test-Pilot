from __future__ import annotations

from pathlib import Path

# A GitHub Actions workflow that re-verifies the committed Kane tests in a real
# browser on every push/PR — using the SAME tool (Kane CLI) that verified them.
# Each committed test ships a replayable `*.md` (Kane test.md); CI replays them.
_CI_WORKFLOW = """name: End-to-End Tests (Kane CLI)
# Re-verifies the committed end-to-end tests in a real browser via Kane CLI on
# every push and pull request. Requires repo secrets LT_USERNAME and
# LT_ACCESS_KEY (Settings -> Secrets and variables -> Actions).
on:
  push:
    branches: ["**"]
  pull_request:
  workflow_dispatch:

jobs:
  kane:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Install Kane CLI
        run: npm install -g @testmuai/kane-cli
      - name: Replay verified tests
        env:
          LT_USERNAME: ${{ secrets.LT_USERNAME }}
          LT_ACCESS_KEY: ${{ secrets.LT_ACCESS_KEY }}
        run: |
          fail=0
          while IFS= read -r -d '' t; do
            echo "::group::$t"
            kane-cli testmd run "$t" --username "$LT_USERNAME" --access-key "$LT_ACCESS_KEY" || fail=1
            echo "::endgroup::"
          done < <(find tests/e2e -name '*.md' ! -name 'README.md' ! -name 'COVERAGE.md' -print0)
          exit $fail
"""


def has_ci(local: Path) -> list[str]:
    """Existing GitHub Actions workflows in the repo (so we can report whether
    we're adding CI to a repo that has none, or alongside existing CI)."""
    wf = local / ".github" / "workflows"
    if not wf.is_dir():
        return []
    return sorted(f.name for f in wf.glob("*.y*ml"))


def generate_ci_workflow(local: Path) -> dict:
    """Write .github/workflows/kane-tests.yml so the repo's CI re-verifies the
    committed Kane tests on every push/PR. Returns {added, existing_ci}.
    Idempotent — a dedicated file that never clobbers the repo's own workflows."""
    existing = has_ci(local)
    wf_dir = local / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / "kane-tests.yml").write_text(_CI_WORKFLOW, encoding="utf-8")
    return {"added": ".github/workflows/kane-tests.yml", "existing_ci": existing}
