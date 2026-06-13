"""Integration tests for .claude/hooks/* — runs the real scripts via subprocess."""

from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import REPO_ROOT, hook_json, run_hook

RUFF = REPO_ROOT / ".venv" / "bin" / "ruff"


@pytest.mark.skipif(not RUFF.exists(), reason="ruff not installed in .venv")
def test_auto_format_reformats_python(tmp_path: Path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("x=1\ny =2\n")  # deliberately mis-formatted

    proc = run_hook("auto_format.py", {"tool_name": "Write", "tool_input": {"file_path": str(target)}})

    assert proc.returncode == 0, proc.stderr
    assert target.read_text() == "x = 1\ny = 2\n"


def test_auto_format_ignores_unknown_extension(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    original = "x=1 (leave me alone)\n"
    target.write_text(original)

    proc = run_hook("auto_format.py", {"tool_name": "Write", "tool_input": {"file_path": str(target)}})

    assert proc.returncode == 0, proc.stderr
    assert target.read_text() == original


def test_auto_format_survives_missing_file(tmp_path: Path) -> None:
    proc = run_hook("auto_format.py", {"tool_name": "Edit", "tool_input": {"file_path": str(tmp_path / "ghost.py")}})
    assert proc.returncode == 0, proc.stderr  # never blocks the agent
