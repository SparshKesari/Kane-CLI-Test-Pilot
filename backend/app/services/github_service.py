from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from ..config import get_settings

# git-over-https can stall indefinitely on an idle socket — every gh/git call
# gets a timeout so a hung clone can't freeze P1 (and the whole run) forever.
_CLONE_TIMEOUT = 180
_GH_TIMEOUT = 90


def _clone(slug: str, dest: Path, env: dict, attempts: int = 2) -> None:
    """Shallow, single-branch clone with a timeout and one retry. We only need
    the current code (not full history), which is faster and avoids the hangs
    seen on large/asset-heavy repos. Cleans a partial clone before retrying."""
    last = ""
    for _ in range(attempts):
        try:
            subprocess.run(
                ["gh", "repo", "clone", slug, str(dest), "--",
                 "--depth=1", "--single-branch"],
                check=True, env=env, capture_output=True, text=True,
                timeout=_CLONE_TIMEOUT,
            )
            return
        except subprocess.TimeoutExpired:
            last = f"clone timed out after {_CLONE_TIMEOUT}s"
        except subprocess.CalledProcessError as e:
            last = ((e.stderr or e.stdout or "") or str(e))[-300:]
        shutil.rmtree(dest, ignore_errors=True)   # drop the partial clone, then retry
    raise RuntimeError(f"git clone failed for {slug}: {last}")


def _slug(repo_url: str) -> str:
    m = re.search(r"github\.com[:/]+([^/]+)/([^/.]+)", repo_url)
    if not m:
        raise ValueError(f"Not a GitHub URL: {repo_url}")
    return f"{m.group(1)}/{m.group(2)}"


def owner_repo(repo_url: str) -> tuple[str, str]:
    owner, name = _slug(repo_url).split("/")
    return owner, name


def fork_and_clone(repo_url: str, branch: str) -> tuple[str, Path]:
    """Get the target onto a working branch. If you OWN the repo, clone it
    directly (you can't fork your own repo) and branch in place. Otherwise fork
    it to your profile and clone the fork.

    Returns (working_repo_url, local_path). Uses `gh` (keyring auth) unless
    GITHUB_TOKEN is set.
    """
    settings = get_settings()
    owner, name = owner_repo(repo_url)
    workspace = Path(settings.workspace_dir).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    dest = workspace / f"{name}-{branch.split('/')[-1]}"

    env = {**os.environ}
    if settings.github_token:
        env["GH_TOKEN"] = settings.github_token

    me = subprocess.run(
        ["gh", "api", "user", "--jq", ".login"],
        check=True, env=env, capture_output=True, text=True, timeout=_GH_TIMEOUT,
    ).stdout.strip()

    if owner.lower() == me.lower():
        target_slug = f"{owner}/{name}"            # own repo — no fork, branch in place
    else:
        subprocess.run(                            # idempotent: reuses an existing fork
            ["gh", "repo", "fork", _slug(repo_url), "--clone=false"],
            check=True, env=env, capture_output=True, text=True, timeout=_GH_TIMEOUT,
        )
        target_slug = f"{me}/{name}"
    target_url = f"https://github.com/{target_slug}"

    if not dest.exists():
        _clone(target_slug, dest, env)
    subprocess.run(["git", "-C", str(dest), "checkout", "-B", branch],
                   check=True, env=env, capture_output=True, text=True, timeout=_GH_TIMEOUT)
    return target_url, dest


def commit_and_pr(local: Path, branch: str, fork_slug: str, title: str, body: str,
                  open_pr: bool = True, extra_paths: list[str] | None = None) -> str:
    """Commit, push the branch to the fork, and (by default) open an INTRA-FORK PR
    (branch → fork's default branch). Intra-fork keeps PRs off the upstream repo."""
    settings = get_settings()
    env = {**os.environ}
    if settings.github_token:
        env["GH_TOKEN"] = settings.github_token

    # Commit ONLY the generated suite — never Kane's .testmuai/ scratch dir.
    gi = local / ".gitignore"
    if ".testmuai/" not in (gi.read_text(encoding="utf-8", errors="ignore") if gi.exists() else ""):
        with gi.open("a", encoding="utf-8") as fh:
            fh.write("\n# Test-tooling working directory\n.testmuai/\n")
    paths = ["tests/e2e", ".gitignore"]
    for p in (extra_paths or []):                  # e.g. HE pipeline + CI workflow
        if (local / p).exists():
            paths.append(p)
    subprocess.run(["git", "-C", str(local), "add", *paths],
                   check=True, env=env, capture_output=True, text=True)
    subprocess.run(["git", "-C", str(local), "commit", "-m", title],
                   env=env, capture_output=True, text=True)  # no-op safe if nothing staged
    subprocess.run(["git", "-C", str(local), "push", "-u", "origin", branch],
                   check=True, env=env, capture_output=True, text=True)
    if not open_pr:
        return f"https://github.com/{fork_slug}/tree/{branch}"

    base = subprocess.run(
        ["gh", "repo", "view", fork_slug, "--json", "defaultBranchRef",
         "-q", ".defaultBranchRef.name"],
        check=True, env=env, capture_output=True, text=True).stdout.strip() or "main"
    return subprocess.run(
        ["gh", "pr", "create", "--repo", fork_slug,
         "--base", base, "--head", branch, "--title", title, "--body", body],
        check=True, env=env, capture_output=True, text=True,
    ).stdout.strip()


def me() -> str:
    return subprocess.run(["gh", "api", "user", "--jq", ".login"],
                          check=True, capture_output=True, text=True).stdout.strip()
