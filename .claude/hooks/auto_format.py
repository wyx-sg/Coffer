#!/usr/bin/env python3
"""PostToolUse hook: format the file Claude just edited. Never blocks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path(__file__).resolve().parents[2]))


def _run(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, cwd=str(REPO), capture_output=True, timeout=60, check=False)
    except Exception:
        pass  # formatting is best-effort; a hook must never break the agent


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
            _run([str(ruff), "format", str(path)])
            _run([str(ruff), "check", "--fix", str(path)])
    elif suffix in {".ts", ".tsx", ".js", ".jsx", ".css", ".json", ".md"}:
        prettier = REPO / "frontend" / "node_modules" / ".bin" / "prettier"
        if prettier.exists():
            _run([str(prettier), "--write", str(path)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
