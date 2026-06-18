#!/usr/bin/env python3
"""PostToolUse hook: format the file Claude just edited. Never blocks.

Python is formatted with the repo's ruff anywhere (ruff is the single Python
authority `make verify` uses). Prettier-managed types are formatted only under
``frontend/``: that is where ``frontend/node_modules/.bin/prettier`` (3.8.x) is
the authority, matching ``make verify``. The rest of the repo's prettier types
(root markdown, yaml, backend json, …) are owned by the pre-commit hook, which
is pinned to a *different* prettier version — formatting them here with the
frontend binary produces churn that CI then fights, so the hook leaves them to
the pinned pre-commit pass.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path(__file__).resolve().parents[2]))
_PRETTIER_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".css", ".json", ".md"}


def _run(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, cwd=str(REPO), capture_output=True, timeout=60, check=False)
    except Exception:
        pass  # formatting is best-effort; a hook must never break the agent


def _under_frontend(path: Path) -> bool:
    try:
        path.resolve().relative_to((REPO / "frontend").resolve())
        return True
    except ValueError:
        return False


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    path_str = (data.get("tool_input") or {}).get("file_path")
    if not path_str:
        return 0
    path = Path(path_str)
    if not path.is_file():
        return 0

    suffix = path.suffix.lower()
    if suffix == ".py":
        ruff = REPO / ".venv" / "bin" / "ruff"
        if ruff.exists():
            # Lint-fix first, then format last so the formatter has the final say
            # on layout (a fix can re-sort imports / rewrite lines).
            _run([str(ruff), "check", "--fix", str(path)])
            _run([str(ruff), "format", str(path)])
    elif suffix in _PRETTIER_SUFFIXES and _under_frontend(path):
        prettier = REPO / "frontend" / "node_modules" / ".bin" / "prettier"
        if prettier.exists():
            _run([str(prettier), "--write", str(path)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
