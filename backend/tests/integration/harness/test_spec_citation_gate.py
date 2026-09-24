"""Tests for scripts/check_spec_citations.py — the requirement-citation gate.

The gate holds two lines: a citation of a requirement names one that exists,
and the retired id forms do not come back. Each rule is proved to bite on a
synthetic tree and to stay quiet on the prose the real tree legitimately uses.

This file is itself scanned by the gate, so every example that must fail is
assembled at runtime (`SPEC`, `CODE` and `SPECS_DIR` below) rather than written
out literally.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from .conftest import REPO_ROOT

_SCRIPT = REPO_ROOT / "scripts" / "check_spec_citations.py"
_NUMBERING = REPO_ROOT / "scripts" / "check_doc_numbering.py"

SPEC = "spec"
CODE = "CODE"
SPECS_DIR = "openspec" + "/specs"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # dataclasses resolve their module through sys.modules.
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gate() -> ModuleType:
    return _load(_SCRIPT, "check_spec_citations")


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        "openspec/specs/knowledge/spec.md",
        "# Knowledge\n\n## Requirements\n\n"
        "### Requirement: Use the file path as a document's identity\ntext\n\n"
        "### Requirement: Keep one tree per collection\ntext\n",
    )
    _write(
        tmp_path,
        "openspec/specs/channels/telegram/spec.md",
        "### Requirement: Download every Telegram media type\ntext\n",
    )
    _write(
        tmp_path,
        "openspec/changes/in-flight/specs/knowledge/spec.md",
        "## ADDED Requirements\n\n### Requirement: Grow a brand new rule\ntext\n\n"
        "## RENAMED Requirements\n\n"
        "- FROM: `### Requirement: Keep one tree per collection`\n"
        "- TO: `### Requirement: Keep exactly one tree per collection`\n",
    )
    _write(
        tmp_path,
        "openspec/changes/archive/2026-01-01-old/specs/knowledge/spec.md",
        "## ADDED Requirements\n\n### Requirement: Something long since archived\ntext\n",
    )
    return tmp_path


def _check(gate: ModuleType, root: Path, text: str, rel: str = "backend/x.py"):
    return gate.check_file(rel, text, gate.load_titles(root))


def _cite(cap: str, title: str, *, comma: str = "") -> str:
    return f'{SPEC} {cap}{comma} "{title}"'


# ---------------------------------------------------------------- rule 1


@pytest.mark.parametrize(
    "text",
    [
        _cite("knowledge", "Use the file path as a document's identity"),
        _cite("knowledge", "Use the file path as a document's identity", comma=","),
        _cite("channels/telegram", "Download every Telegram media type"),
        # Wrapped across `#` comment lines, both between tokens and inside the title.
        f'# ... ({SPEC}\n# knowledge "Use the file path as a\n# document\'s identity").',
        # Wrapped inside a docstring: the continuation has no leader.
        f'"""... ({SPEC} knowledge "Use the file path\n    as a document\'s identity")."""',
        f'// {SPEC} knowledge\n// "Use the file path as a document\'s identity"',
        f" * {SPEC} knowledge “Use the file path as a document's identity”",
        f"({SPEC} knowledge, 'Keep one tree per collection')",
        f'[knowledge](../../{SPECS_DIR}/knowledge/spec.md) "Keep one tree per collection"',
        f'[knowledge](../{SPECS_DIR}/knowledge/spec.md),\n  "Keep one tree per collection"',
    ],
)
def test_a_citation_of_an_existing_requirement_passes(gate, tree, text) -> None:
    errors, _ = _check(gate, tree, text)
    assert errors == []
    assert len(gate.find_citations(text)) == 1


def test_a_title_the_spec_does_not_have_fails(gate, tree) -> None:
    errors, _ = _check(gate, tree, "# " + _cite("knowledge", "Keep two trees per collection"))
    assert len(errors) == 1
    assert "has no requirement titled 'Keep two trees per collection'" in errors[0]


def test_a_wrapped_title_is_compared_as_one_line(gate, tree) -> None:
    text = f'# ({SPEC} knowledge "Use the file path as\n# the identity of a document")'
    errors, _ = _check(gate, tree, text)
    assert len(errors) == 1
    assert "'Use the file path as the identity of a document'" in errors[0]


def test_a_capability_that_does_not_exist_fails(gate, tree) -> None:
    errors, _ = _check(gate, tree, _cite("knowlege", "Keep one tree per collection"))
    assert len(errors) == 1
    assert "no capability 'knowlege'" in errors[0]


def test_a_child_is_its_own_capability(gate, tree) -> None:
    """A parent's title is not a child's, and a child that does not exist fails."""
    errors, _ = _check(gate, tree, _cite("channels/telegram", "Keep one tree per collection"))
    assert len(errors) == 1
    errors, _ = _check(gate, tree, _cite("channels/seatalk", "Download every Telegram media type"))
    assert len(errors) == 1 and "no capability 'channels/seatalk'" in errors[0]


def test_a_link_citation_is_checked_by_its_path(gate, tree) -> None:
    bad_title = f'[knowledge](../{SPECS_DIR}/knowledge/spec.md) "Keep no tree at all"'
    bad_cap = f'[x](../{SPECS_DIR}/knowlege/spec.md) "Keep one tree per collection"'
    assert len(_check(gate, tree, bad_title)[0]) == 1
    assert "no capability 'knowlege'" in _check(gate, tree, bad_cap)[0][0]


def test_a_title_an_in_flight_change_adds_is_noted_not_failed(gate, tree) -> None:
    for title in ("Grow a brand new rule", "Keep exactly one tree per collection"):
        errors, notes = _check(gate, tree, _cite("knowledge", title))
        assert errors == []
        assert len(notes) == 1 and "openspec/changes/in-flight/" in notes[0]


def test_an_archived_change_supplies_no_titles(gate, tree) -> None:
    errors, _ = _check(gate, tree, _cite("knowledge", "Something long since archived"))
    assert len(errors) == 1


def test_citing_a_title_a_change_renames_away_is_noted(gate, tree) -> None:
    errors, notes = _check(gate, tree, _cite("knowledge", "Keep one tree per collection"))
    assert errors == []
    assert len(notes) == 1 and "before that change is archived" in notes[0]


def test_a_change_folder_may_cite_its_own_delta_titles(gate, tree) -> None:
    rel = "openspec/changes/in-flight/design.md"
    errors, notes = _check(gate, tree, _cite("knowledge", "Grow a brand new rule"), rel)
    assert errors == [] and notes == []


@pytest.mark.parametrize(
    "text",
    [
        # An error-code map under a `# spec <cap>` label: a key, not a title.
        f'    # {SPEC} knowledge\n    "KNOWLEDGE_NOT_FOUND": 404,',
        # Prose that happens to follow "spec" with a quote.
        f'the {SPEC} scenario "desktop app agents list"',
        f"{SPEC} knowledge's overview draws the boundary",
        f"{SPEC} knowledge ``## Purpose``",
        f"the {SPEC} for `key`",
    ],
)
def test_legitimate_prose_is_not_a_citation(gate, tree, text) -> None:
    assert gate.find_citations(text) == []
    assert _check(gate, tree, text) == ([], [])


# ---------------------------------------------------------------- rule 2


@pytest.mark.parametrize(
    "text",
    [
        f"see {SPEC} vault-sync E3 for the reason",
        f"({SPEC} channels, D1a)",
        f"raises {CODE}-027 on a bad env",
        f"registered under {CODE}-REG",
        f"as SPEC{'-'}012 requires",
    ],
)
def test_each_retired_id_form_fails(gate, tree, text) -> None:
    errors, _ = _check(gate, tree, text)
    assert len(errors) == 1


@pytest.mark.parametrize(
    "text",
    [
        f"{SPEC} vault-sync slice 7",
        f"the {SPEC} daemon HTTP surface",
        f"{CODE}-1234 is a port, not an id",
        "SPEC_ID = 'x'",
        f"a {CODE}-REGISTRY key",
    ],
)
def test_text_that_only_resembles_a_retired_id_passes(gate, tree, text) -> None:
    assert _check(gate, tree, text) == ([], [])


def test_a_change_folder_may_name_a_retired_id(gate, tree) -> None:
    rel = "openspec/changes/in-flight/proposal.md"
    assert _check(gate, tree, f"replaces {CODE}-027", rel) == ([], [])


def test_numbered_spec_rejects_every_case() -> None:
    numbering = _load(_NUMBERING, "check_doc_numbering")
    for text in (f"{SPEC} 004", f"{SPEC}s 009", f"SPEC{'-'}012", f"{SPEC}-001"):
        assert numbering.NUMBERED_SPEC.search(text), text
    assert not numbering.NUMBERED_SPEC.search(f"{SPEC} 2026")
