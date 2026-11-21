"""Tests for scripts/check_frontend_agent_types.py — the web UI's agent-name gate.

The gate fails on an agent type's value written as a string literal or an
object key in ``frontend/src/`` outside the agent modules and the files that
hold a per-agent value the daemon does not serve. Each form is proved to bite
on synthetic source and to stay quiet on look-alikes; the real tree is clean.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from types import ModuleType

import pytest

from .conftest import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "check_frontend_agent_types.py"


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_frontend_agent_types", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_frontend_agent_types"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_reads_every_agent_type_from_the_enum(gate: ModuleType) -> None:
    values = gate.agent_type_values()
    assert "claude_code" in values and "codex" in values and "cursor" in values


@pytest.mark.parametrize(
    "source",
    [
        'if (agent.type === "codex") return;',
        "const AGENTS = ['claude_code', 'codex'];",
        "const wire = {\n  claude_code: 'anthropic',\n};",
        "const k = `opencode`;",
        'if (t === "cursor") {}',
    ],
)
@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="an agent named outside the web UI's agent modules fails the lint gate",
)
def test_flags_an_agent_named_by_its_value(gate: ModuleType, source: str) -> None:
    assert gate.scan_source(source, gate.agent_type_values())


@pytest.mark.parametrize(
    "source",
    [
        "// codex reads ~/.agents/skills",
        "const page = { cursor: next };",
        'const label = "Codex";',
        "const codexHome = dir;",
    ],
)
def test_ignores_look_alikes(gate: ModuleType, source: str) -> None:
    assert gate.scan_source(source, gate.agent_type_values()) == []


def test_the_tree_is_clean() -> None:
    done = subprocess.run([sys.executable, str(_SCRIPT)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
