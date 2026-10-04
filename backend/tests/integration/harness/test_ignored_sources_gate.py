"""Tests for scripts/check_ignored_sources.py — the hidden-source-file gate.

The gate fails when a `.gitignore` rule hides a path in a source tree, and on
an unanchored pattern that names a common source-folder word. Each check is
proved on a throwaway repository under `tmp_path`, and the real tree is proved
clean.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from .conftest import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "check_ignored_sources.py"


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_ignored_sources", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_ignored_sources"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write(root: Path, rel: str, text: str = "x\n") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    return tmp_path


def test_an_unanchored_rule_hiding_a_source_folder_fails_with_the_rule(gate, repo) -> None:
    _write(repo, ".gitignore", "# venvs\n/.venv\nenv/\n")
    _write(repo, "frontend/src/components/mcp/env/EnvRow.tsx")
    errors = gate.check(repo)
    hidden = [e for e in errors if e.startswith("frontend/src/components/mcp/env/")]
    assert len(hidden) == 1
    assert ".gitignore:3: env/" in hidden[0]


def test_a_rule_matches_a_folder_of_another_case(gate, repo) -> None:
    # Git is asked with core.ignorecase=true, so a Linux run finds what macOS hides.
    _write(repo, ".gitignore", "/ENV/\nSecrets/\n")
    _write(repo, "backend/coffer/secrets/store.py")
    assert gate.hidden_paths(repo) == ["backend/coffer/secrets/store.py"]


def test_a_tracked_file_under_an_ignore_rule_fails(gate, repo) -> None:
    _write(repo, "scripts/lib/helper.py")
    subprocess.run(["git", "add", "scripts/lib/helper.py"], cwd=repo, check=True)
    _write(repo, ".gitignore", "/lib/\nscripts/lib/\n")
    assert gate.hidden_paths(repo) == ["scripts/lib/helper.py"]


def test_generated_and_cache_output_is_expected(gate, repo) -> None:
    _write(
        repo,
        ".gitignore",
        "__pycache__/\n*.pyc\nnode_modules\ndist/\ntest-results/\n.vitepress/cache/\n*.egg-info/\n",
    )
    _write(repo, "backend/coffer/__pycache__/a.cpython-312.pyc")
    _write(repo, "backend/tests/b.pyc")
    _write(repo, "e2e/node_modules/pkg/index.js")
    _write(repo, "e2e/visual/test-results/diff.png")
    _write(repo, "docs-site/.vitepress/cache/deps.json")
    _write(repo, "frontend/src/dist/bundle.js")
    _write(repo, "backend/coffer.egg-info/PKG-INFO")
    assert gate.hidden_paths(repo) == []


def test_paths_outside_the_source_trees_are_not_scanned(gate, repo) -> None:
    _write(repo, ".gitignore", "/.coffer/\n")
    _write(repo, ".coffer/state.json")
    assert gate.hidden_paths(repo) == []


@pytest.mark.parametrize(
    ("line", "flagged"),
    [
        ("env/", True),
        ("lib/", True),
        ("build", True),
        ("SECRETS/", True),
        ("vendor/", True),
        ("/build/", False),
        ("backend/build/", False),
        ("!frontend/src/lib/", False),
        ("# lib/", False),
        ("node_modules", False),
        ("*.log", False),
    ],
)
def test_an_unanchored_source_word_pattern_is_flagged(gate, tmp_path, line, flagged) -> None:
    ignore = tmp_path / ".gitignore"
    ignore.write_text(f"{line}\n", encoding="utf-8")
    errors = gate.risky_patterns(ignore, ".gitignore")
    assert bool(errors) is flagged, errors
    if flagged:
        assert errors[0].startswith(".gitignore:1:")


def test_the_real_tree_is_clean() -> None:
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT)], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60
    )
    assert proc.returncode == 0, proc.stderr
