"""Tests for scripts/check_agent_type_branches.py — the agent-branch gate.

The gate fails on code in ``backend/coffer/`` outside the agent descriptor and
its facet implementations that names an agent type (ADR
agent-mechanisms-are-optional-facets-on-the-descriptor). Each rule is proved to
bite on synthetic source and to stay quiet on code that only looks similar; the
real tree is proved clean and the allowed places exempt.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from .conftest import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "check_agent_type_branches.py"


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_agent_type_branches", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_agent_type_branches"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def members(gate: ModuleType) -> dict[str, str]:
    return dict(gate.agent_type_values())


def test_the_members_are_read_from_the_enum(members: dict[str, str]) -> None:
    assert members == {"CLAUDE_CODE": "claude_code", "CODEX": "codex"}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("if t is AgentType.CODEX:\n    pass\n", ["AgentType.CODEX"]),
        ("x = {AgentType.CLAUDE_CODE: 1}\n", ["AgentType.CLAUDE_CODE"]),
        (
            "from coffer.domain.agent.types import AgentType as T\nok = t == T.CODEX\n",
            ["T.CODEX"],
        ),
        ('if key == "claude_code":\n    pass\n', ["comparison with 'claude_code'"]),
        ('ok = "codex" != key\n', ["comparison with 'codex'"]),
        ('ok = key in ("codex",)\n', []),
        ('match key:\n    case "codex":\n        pass\n', ["match case 'codex'"]),
    ],
)
def test_each_agent_branch_is_caught(
    gate: ModuleType, members: dict[str, str], source: str, expected: list[str]
) -> None:
    assert [what for _line, what in gate.scan_source(source, members)] == expected


@pytest.mark.parametrize(
    "source",
    [
        # Constructing a member from a value says nothing about which agent.
        "t = AgentType(value)\n",
        "types = list(AgentType)\n",
        "for t in AgentType:\n    pass\n",
        # A string that merely equals a value, not compared.
        'agent_key = "codex"\n',
        # A different enum's member with the same attribute name.
        "x = PluginModel.CODEX\n",
        # Other attributes of AgentType.
        "x = AgentType.__members__\n",
    ],
)
def test_similar_code_is_not_flagged(
    gate: ModuleType, members: dict[str, str], source: str
) -> None:
    assert gate.scan_source(source, members) == []


def test_the_allowed_places_are_exempt(gate: ModuleType) -> None:
    root = gate.PACKAGE_DIR
    assert gate._is_allowed(root / "domain" / "agent" / "descriptor.py")
    assert gate._is_allowed(root / "infrastructure" / "agent" / "model_discovery.py")
    assert gate._is_allowed(root / "infrastructure" / "memory" / "delivery" / "codex.py")
    assert gate._is_allowed(root / "domain" / "provider" / "agent_projection.py")
    assert not gate._is_allowed(root / "application" / "provider" / "service.py")
    assert not gate._is_allowed(root / "domain" / "provider" / "projection.py")


def test_the_real_tree_is_clean() -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_a_violation_fails_the_build(
    gate: ModuleType, members: dict[str, str], tmp_path: Path
) -> None:
    pkg = tmp_path / "application"
    pkg.mkdir()
    (pkg / "bad.py").write_text("if t is AgentType.CODEX:\n    pass\n", encoding="utf-8")
    found = gate.scan_tree(tmp_path, members)
    assert [(p.name, what) for p, _line, what in found] == [("bad.py", "AgentType.CODEX")]
