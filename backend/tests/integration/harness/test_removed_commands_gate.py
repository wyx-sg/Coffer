"""Tests for scripts/check_removed_commands.py — no reader is told to run a
command that no longer exists.

The removed spellings are assembled at runtime, because this file sits in no
scanned tree today but must not start failing the gate if one grows to hold it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from .conftest import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "check_removed_commands.py"
DIAGNOSE = "coffer" + "__diagnose"
MEMORY_CONTEXT = "coffer memory " + "context"


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_removed_commands", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_removed_commands"] = mod
    spec.loader.exec_module(mod)
    return mod


def _scanned(gate: ModuleType) -> set[str]:
    return {p.relative_to(gate.REPO_ROOT).as_posix() for p in gate._files()}


def test_the_chinese_readme_the_repo_docs_and_the_desktop_shell_are_scanned(gate) -> None:
    scanned = _scanned(gate)
    assert "README.zh-CN.md" in scanned
    assert "desktop/src/logging.rs" in scanned
    assert any(p.startswith("docs/research/") for p in scanned)


def test_the_adrs_are_history_and_are_not_scanned(gate) -> None:
    assert not [p for p in _scanned(gate) if p.startswith("docs/decisions/")]


@pytest.mark.parametrize(
    ("rel", "line", "phrase"),
    [
        ("desktop/src/fake.rs", f"//! read by `{DIAGNOSE}`", DIAGNOSE),
        ("docs/research/fake.md", f"run `{MEMORY_CONTEXT} --agent-uid x`", MEMORY_CONTEXT),
    ],
)
def test_a_removed_command_in_a_newly_scanned_tree_fails(
    gate, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rel: str, line: str, phrase: str
) -> None:
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    path = tmp_path / rel
    path.parent.mkdir(parents=True)
    path.write_text(line + "\n", encoding="utf-8")
    (hit,) = gate.scan([path], allowed=())
    assert hit.startswith(f"{rel}:1: removed `{phrase}`")
