from __future__ import annotations

import re
from pathlib import Path

# Directories that never contain meaningful page/flow source.
_SKIP_DIRS = {
    ".git", "node_modules", ".next", ".nuxt", "dist", "build", "out", "coverage",
    "public", "static", "assets", ".turbo", ".cache", "__pycache__", ".venv",
    "venv", "vendor", "tests", "test", "e2e", "__tests__", "cypress", ".github",
}
# Source we care about: UI pages, components, routes, data, server views.
_SRC_EXT = {".tsx", ".jsx", ".ts", ".js", ".vue", ".svelte", ".astro",
            ".html", ".py", ".rb", ".php"}
# Noise even when the extension matches.
_SKIP_FILE = re.compile(
    r"(\.d\.ts$|\.test\.|\.spec\.|\.stories\.|\.config\.|\.min\.|"
    r"setup\.|jest\.|vitest\.|eslint|prettier|tailwind|postcss|webpack|vite\.config)",
    re.I,
)


def _priority(rel: str) -> int:
    """Lower sorts first — page/route files beat components beat data beat the rest."""
    p = rel.lower()
    if "/api/" in p:
        return 4                                   # server endpoints — context, not a UI flow
    if re.search(r"(^|/)(app|pages)/.*(page|layout|index|\+page)\.", p):
        return 0                                   # framework page/route entrypoints
    if "/pages/" in p or "/app/" in p or "/routes/" in p or "/views/" in p:
        return 1
    if "/components/" in p or "/ui/" in p:
        return 2
    if re.search(r"(data|content|catalog|constant|fixtures?|seed|store|context)", p):
        return 3                                   # the catalog/entities the UI renders
    if "/src/" in p or "/lib/" in p or "/hooks/" in p:
        return 4
    return 5


def routes(local: Path) -> list[str]:
    """Best-effort navigable routes from file-based routing (Next app/ + pages/).
    Dynamic segments ([id]) are kept as-is so the strategist knows they exist."""
    found: set[str] = set()
    for base in ("app", "src/app"):
        root = local / base
        if root.is_dir():
            for f in root.rglob("page.*"):
                if _skip(f, local):
                    continue
                rel = f.parent.relative_to(root).as_posix()
                found.add("/" + ("" if rel == "." else rel))
    for base in ("pages", "src/pages"):
        root = local / base
        if root.is_dir():
            for f in root.rglob("*.*"):
                if f.suffix not in {".tsx", ".jsx", ".ts", ".js"} or _skip(f, local):
                    continue
                name = f.stem
                if name.startswith("_") or "/api/" in f.as_posix():
                    continue
                rel = f.relative_to(root).with_suffix("").as_posix()
                rel = re.sub(r"/index$", "", rel)
                found.add("/" + ("" if rel == "index" else rel))
    return sorted(found)[:40]


def _skip(f: Path, local: Path) -> bool:
    parts = set(f.relative_to(local).parts)
    return bool(parts & _SKIP_DIRS) or bool(_SKIP_FILE.search(f.name))


def collect(local: Path, *, max_files: int = 20, per_file: int = 6000,
            total_cap: int = 48000) -> dict:
    """Read the highest-signal page/flow source from the cloned repo, bounded so
    the P4 prompt stays affordable. Returns routes + a list of {path, content}.
    The LLM reads this to ground scenarios in real routes, exact rendered strings,
    and conditional/empty/error states — behavior a DOM snapshot can't reveal."""
    candidates: list[Path] = []
    for f in local.rglob("*"):
        if not f.is_file() or f.suffix not in _SRC_EXT or _skip(f, local):
            continue
        try:
            if f.stat().st_size > 64_000:          # skip huge generated files
                continue
        except OSError:
            continue
        candidates.append(f)

    candidates.sort(key=lambda f: (_priority(f.relative_to(local).as_posix()),
                                   f.relative_to(local).as_posix()))
    files, used = [], 0
    for f in candidates[: max_files * 2]:
        if len(files) >= max_files or used >= total_cap:
            break
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        snippet = text[:per_file]
        used += len(snippet)
        files.append({"path": f.relative_to(local).as_posix(), "content": snippet})

    return {"routes": routes(local), "files": files, "files_read": len(files)}
