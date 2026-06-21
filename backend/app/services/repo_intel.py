from __future__ import annotations

import ast
from pathlib import Path

from ..models import ExistingTest

_TEST_DIR_HINTS = ("tests", "test", "e2e", "spec", "__tests__")
# "test.py" catches Kane's as_is export (tests/e2e/<name>/test.py); the others
# catch conventional pytest/vanilla-Playwright names.
_PY_TEST_GLOBS = ("test_*.py", "*_test.py", "test.py")
_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}


def profile(local: Path) -> dict:
    """P2: lightweight framework/route detection from the cloned repo."""
    has = lambda *p: any((local / x).exists() for x in p)
    frameworks = []
    if has("pytest.ini", "pyproject.toml", "setup.cfg") \
            or any(local.rglob(g) for g in _PY_TEST_GLOBS):
        frameworks.append("pytest")
    if list(local.rglob("*.spec.ts")) or list(local.rglob("playwright.config.*")):
        frameworks.append("playwright")
    if (local / "package.json").exists():
        frameworks.append("node")
    test_dirs = sorted({
        str(p.relative_to(local)) for h in _TEST_DIR_HINTS
        for p in local.rglob(h) if p.is_dir() and ".git" not in p.parts
    })
    return {
        "frameworks": frameworks or ["unknown"],
        "test_dirs": test_dirs[:10],
        "language": "python" if "pytest" in frameworks else "unknown",
    }


def inventory(local: Path) -> list[ExistingTest]:
    """P3: AST-walk python test files into a normalized index."""
    out: list[ExistingTest] = []
    seen: set[Path] = set()
    for glob in _PY_TEST_GLOBS:
        for f in local.rglob(glob):
            if f in seen or _SKIP_DIRS & set(f.parts):
                continue
            seen.add(f)
            try:
                tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                # Kane exports `async def test(...)`, so accept async defs too.
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and node.name.startswith("test"):
                    out.append(ExistingTest(
                        file=str(f.relative_to(local)),
                        name=node.name,
                        framework="pytest",
                        target=_docstring_first_line(node),
                    ))
    return out


def _docstring_first_line(node: ast.FunctionDef) -> str:
    doc = ast.get_docstring(node) or ""
    return doc.splitlines()[0] if doc else ""
