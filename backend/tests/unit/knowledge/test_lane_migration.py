"""Unit tests for the one-time seven-lanes → two-lanes on-disk migration.

The migration is destructive by explicit decision: ``rules/``, ``handoff/``,
``superseded/``, ``consolidation-log.md`` and ``INDEX.md`` are removed with no
holding pen. Everything that carries content moves instead, so the tests here
are mostly about what must NOT be lost — every note from both old entry
directories, the ingested markdown, and the ``.raw/`` originals — and about the
sweep being safely re-runnable, since it runs best-effort at every daemon start.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from coffer.infrastructure.knowledge_scope.lane_migration import (
    LaneMigrationReport,
    migrate_knowledge_root,
    migrate_scope,
)


def _old_scope(root: Path, name: str = "global") -> Path:
    """A scope directory in the pre-2026-09-11 seven-lane layout."""
    scope = root / name
    (scope / "knowledge" / "inbox").mkdir(parents=True)
    (scope / "knowledge" / "git-notes.md").write_text("TOPIC_DOC\n", encoding="utf-8")
    (scope / "knowledge" / "INDEX.md").write_text("# Index\n", encoding="utf-8")
    (scope / "knowledge" / "inbox" / "raw-item.md").write_text("STAGED_ITEM\n", encoding="utf-8")
    (scope / "inbox").mkdir()
    (scope / "inbox" / "handbook.md").write_text("INGESTED_DOC\n", encoding="utf-8")
    (scope / ".raw").mkdir()
    (scope / ".raw" / "handbook.pdf").write_bytes(b"%PDF-ORIGINAL")
    (scope / "rules").mkdir()
    (scope / "rules" / "ci.md").write_text("- always verify\n", encoding="utf-8")
    (scope / "handoff").mkdir()
    (scope / "handoff" / "work.md").write_text("scene\n", encoding="utf-8")
    (scope / "superseded").mkdir()
    (scope / "superseded" / "old-topic-20260101T000000.md").write_text("old\n", encoding="utf-8")
    (scope / "consolidation-log.md").write_text("# Log\n", encoding="utf-8")
    return scope


def _names(directory: Path) -> list[str]:
    return sorted(p.name for p in directory.iterdir())


# --- one scope --------------------------------------------------------------


@pytest.mark.acceptance(
    spec="knowledge",
    scenario="the two-lane migration flattens the old lanes",
)
def test_old_layout_becomes_two_lanes_plus_two_hidden_archives(tmp_path: Path) -> None:
    scope = _old_scope(tmp_path)
    report = LaneMigrationReport()

    migrate_scope(scope, report)

    # Both old entry directories flattened into ONE notes lane.
    assert _names(scope / "notes") == ["git-notes.md", "raw-item.md"]
    assert (scope / "notes" / "git-notes.md").read_text() == "TOPIC_DOC\n"
    assert (scope / "notes" / "raw-item.md").read_text() == "STAGED_ITEM\n"

    # The ingested lane is renamed, content untouched.
    assert _names(scope / "docs") == ["handbook.md"]
    assert (scope / "docs" / "handbook.md").read_text() == "INGESTED_DOC\n"

    # The originals are not the migration's business.
    assert (scope / ".raw" / "handbook.pdf").read_bytes() == b"%PDF-ORIGINAL"

    # Everything that does not survive is gone, INDEX.md included.
    for gone in ("knowledge", "inbox", "rules", "handoff", "superseded", "consolidation-log.md"):
        assert not (scope / gone).exists(), gone
    assert not (scope / "notes" / "INDEX.md").exists()

    assert _names(scope) == [".raw", "docs", "notes"]
    assert report.scopes_migrated == 1
    assert report.notes_moved == 2
    assert report.retired_removed == 4  # rules/, handoff/, superseded/, the log


def test_a_basename_collision_keeps_both_files(tmp_path: Path) -> None:
    """A staged item and a topic doc can share a basename and still be
    different text. Neither may be dropped, and the consolidated topic doc —
    the more considered of the two — keeps the unsuffixed name."""
    scope = tmp_path / "global"
    (scope / "knowledge" / "inbox").mkdir(parents=True)
    (scope / "knowledge" / "git-notes.md").write_text("CONSOLIDATED\n", encoding="utf-8")
    (scope / "knowledge" / "inbox" / "git-notes.md").write_text("STAGED\n", encoding="utf-8")
    report = LaneMigrationReport()

    migrate_scope(scope, report)

    assert _names(scope / "notes") == ["git-notes-2.md", "git-notes.md"]
    assert (scope / "notes" / "git-notes.md").read_text() == "CONSOLIDATED\n"
    assert (scope / "notes" / "git-notes-2.md").read_text() == "STAGED\n"
    assert report.notes_moved == 2


def test_ingested_lane_merges_into_an_existing_docs_dir(tmp_path: Path) -> None:
    """A half-migrated scope (``docs/`` already there, ``inbox/`` still there)
    must merge rather than fail or clobber — the sweep is best-effort, so it
    can be interrupted partway."""
    scope = tmp_path / "global"
    (scope / "docs").mkdir(parents=True)
    (scope / "docs" / "already.md").write_text("ALREADY\n", encoding="utf-8")
    (scope / "inbox").mkdir()
    (scope / "inbox" / "late.md").write_text("LATE\n", encoding="utf-8")
    report = LaneMigrationReport()

    migrate_scope(scope, report)

    assert _names(scope / "docs") == ["already.md", "late.md"]
    assert not (scope / "inbox").exists()


def test_a_scope_already_on_the_new_layout_is_untouched(tmp_path: Path) -> None:
    scope = tmp_path / "global"
    (scope / "notes").mkdir(parents=True)
    (scope / "notes" / "kept.md").write_text("KEPT\n", encoding="utf-8")
    (scope / "docs").mkdir()
    (scope / "docs" / "doc.md").write_text("DOC\n", encoding="utf-8")
    (scope / ".history").mkdir()
    (scope / ".history" / "kept-20260910T090000.md").write_text("OLD\n", encoding="utf-8")
    report = LaneMigrationReport()

    migrate_scope(scope, report)

    assert report.did_work is False
    assert report.scopes_migrated == 0
    assert _names(scope) == [".history", "docs", "notes"]
    assert (scope / "notes" / "kept.md").read_text() == "KEPT\n"
    assert (scope / ".history" / "kept-20260910T090000.md").read_text() == "OLD\n"


def test_a_second_pass_is_a_no_op(tmp_path: Path) -> None:
    """Idempotent: the sweep runs at every daemon start, so the boot after the
    migrating one must find nothing to do and change nothing."""
    scope = _old_scope(tmp_path)
    migrate_scope(scope, LaneMigrationReport())
    after_first = {p: p.read_bytes() for p in sorted(scope.rglob("*")) if p.is_file()}

    second = LaneMigrationReport()
    migrate_scope(scope, second)

    assert second.did_work is False
    assert {p: p.read_bytes() for p in sorted(scope.rglob("*")) if p.is_file()} == after_first


# --- the root sweep ---------------------------------------------------------


def test_sweep_migrates_every_scope_and_skips_hidden_entries(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    root.mkdir()
    _old_scope(root, "global")
    _old_scope(root, "project-01ABC")
    (root / ".DS_Store").write_text("junk", encoding="utf-8")
    (root / "loose-file.md").write_text("not a scope", encoding="utf-8")

    report = migrate_knowledge_root(root)

    assert report.scopes_migrated == 2
    assert report.notes_moved == 4
    assert report.failures == []
    for name in ("global", "project-01ABC"):
        assert _names(root / name) == [".raw", "docs", "notes"]
    assert (root / "loose-file.md").read_text() == "not a scope"


def test_sweep_over_a_missing_root_is_a_clean_no_op(tmp_path: Path) -> None:
    report = migrate_knowledge_root(tmp_path / "nothing-here")
    assert report.did_work is False
    assert report.failures == []


def test_one_failing_scope_is_recorded_and_the_sweep_continues(tmp_path: Path, monkeypatch) -> None:
    """A half-migrated vault is still readable, so one bad scope must never
    abort the boot sweep — it is recorded and the rest still migrate."""
    root = tmp_path / "knowledge"
    root.mkdir()
    _old_scope(root, "a-broken")
    _old_scope(root, "b-fine")

    real_move = shutil.move

    def flaky_move(src: str, dst: str) -> object:
        if "a-broken" in str(src):
            raise OSError("permission denied")
        return real_move(src, dst)

    monkeypatch.setattr(
        "coffer.infrastructure.knowledge_scope.lane_migration.shutil.move", flaky_move
    )

    report = migrate_knowledge_root(root)

    assert [f.split(":")[0] for f in report.failures] == ["a-broken"]
    assert "permission denied" in report.failures[0]
    assert _names(root / "b-fine") == [".raw", "docs", "notes"]
