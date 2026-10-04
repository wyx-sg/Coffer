"""Tests for scripts/ci_change_scope.py — which pull requests skip the test jobs.

verify.yml skips the backend and frontend test jobs for a change that only
touches prose no test reads. A wrong "prose" verdict merges untested code, so
the cases that matter most are the ones that must still count as code.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys

import pytest

from .conftest import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "ci_change_scope.py"


def _load():
    spec = importlib.util.spec_from_file_location("ci_change_scope", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


scope = _load()


@pytest.mark.parametrize(
    "path",
    [
        "docs/decisions/some-decision.md",
        "docs-site/architecture/overview.md",
        "docs-site/.vitepress/config.mts",
        "CONTRIBUTING.md",
        "./SECURITY.md",
    ],
)
def test_documentation_no_test_reads_is_prose(path: str) -> None:
    assert scope.is_prose(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "openspec/specs/channels/spec.md",  # validated + scenario-audited
        ".agents/testing.md",
        ".claude/skills/x/SKILL.md",
        "backend/coffer/application/knowledge/skill_assets/guide.md",  # ships in the package
        "frontend/README.md",
        "e2e/README.md",
        "evals/README.md",
        "README.md",  # a distribution test asserts on it
        "docs-site/public/install.sh",  # a test runs it
        "backend/coffer/app.py",
        "Makefile",
        ".github/workflows/verify.yml",
    ],
)
def test_files_a_test_or_gate_reads_are_code(path: str) -> None:
    assert scope.is_prose(path) is False


def test_one_code_file_among_docs_needs_the_tests() -> None:
    assert scope.needs_tests(["docs/a.md", "backend/coffer/app.py", "docs-site/b.md"]) is True


def test_a_docs_only_change_skips_the_tests() -> None:
    assert scope.needs_tests(["docs/a.md\n", "docs-site/b.md\n", "\n"]) is False


def test_an_empty_change_list_needs_the_tests() -> None:
    assert scope.needs_tests([]) is True
    assert scope.needs_tests(["\n", "  "]) is True


def test_the_script_prints_a_github_output_line() -> None:
    docs = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        input="docs/a.md\nCONTRIBUTING.md\n",
        capture_output=True,
        text=True,
        check=True,
    )
    code = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        input="docs/a.md\nbackend/coffer/app.py\n",
        capture_output=True,
        text=True,
        check=True,
    )
    assert docs.stdout == "code=false\n"
    assert code.stdout == "code=true\n"
