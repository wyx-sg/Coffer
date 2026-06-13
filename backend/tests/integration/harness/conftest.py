"""Fixtures for testing the .claude/hooks/* scripts via subprocess."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# backend/tests/integration/harness/conftest.py -> repo root is parents[4]
REPO_ROOT = Path(__file__).resolve().parents[4]
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"


def run_hook(
    script_name: str, payload: dict, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a hook script with `payload` as JSON on stdin, return the completed process."""
    script = HOOKS_DIR / script_name
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd or REPO_ROOT),
        timeout=60,
    )


def hook_json(proc: subprocess.CompletedProcess[str]) -> dict:
    """Parse a hook's stdout JSON; return {} when stdout is empty."""
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


@pytest.fixture
def run_hook_fn():
    return run_hook


@pytest.fixture
def hook_json_fn():
    return hook_json
