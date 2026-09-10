"""Unit tests for the ``notes/`` lane I/O — and above all for its archive.

``.history/`` is the ENTIRE safety net under the tidy pass: an LLM rewrites and
merges notes unattended, with no review step and no diff to approve. So the
archive gets the hard tests here — ordering (archive lands before the new bytes
do), fidelity (the archived copy holds the OLD text, read from disk), collision
(two archives of one slug in the same second), the missing-note case, and the
traversal guard — and the read/list/delete paths get the ordinary ones.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from coffer.infrastructure.knowledge import fs as knowledge_fs
from coffer.infrastructure.knowledge.paths import history_dir, note_path, notes_dir
from coffer.infrastructure.knowledge_scope import note_files
from coffer.infrastructure.knowledge_scope.note_files import (
    archive_note,
    delete_note,
    list_notes,
    note_exists,
    read_note,
    write_note,
)

_T0 = datetime(2026, 9, 11, 12, 0, 0, tzinfo=UTC)
_T1 = datetime(2026, 9, 11, 13, 30, 0, tzinfo=UTC)


def _write(store: Path, slug: str, body: str, *, now: datetime = _T0) -> Path:
    return write_note(store, slug, title=slug.title(), summary=f"about {slug}", body=body, now=now)


# --- write + read roundtrip -------------------------------------------------


def test_write_then_read_roundtrips_the_note(tmp_path: Path) -> None:
    store = tmp_path / "scope"
    path = _write(store, "deploy", "Deploy via `make release`.")

    assert path == note_path(store, "deploy")
    assert path.parent == notes_dir(store)

    doc = read_note(store, "deploy")
    assert doc is not None
    assert doc.slug == "deploy"
    assert doc.title == "Deploy"
    assert doc.summary == "about deploy"
    assert doc.body == "Deploy via `make release`."
    assert doc.updated_at == _T0


def test_read_missing_note_is_none(tmp_path: Path) -> None:
    assert read_note(tmp_path / "scope", "nope") is None


def test_read_degrades_for_a_hand_written_note(tmp_path: Path) -> None:
    """A note typed straight into the lane has no frontmatter: the stem stands
    in for the title, the summary is "" (not a guess at one) and the mtime
    stands in for the timestamp."""
    store = tmp_path / "scope"
    path = note_path(store, "by-hand")
    path.parent.mkdir(parents=True)
    path.write_text("Just a line I typed.\n", encoding="utf-8")

    doc = read_note(store, "by-hand")
    assert doc is not None
    assert doc.title == "by-hand"
    assert doc.summary == ""
    assert doc.body == "Just a line I typed."
    assert doc.updated_at is not None  # fell back to the file mtime


def test_note_exists_tracks_the_file(tmp_path: Path) -> None:
    store = tmp_path / "scope"
    assert note_exists(store, "deploy") is False
    _write(store, "deploy", "x")
    assert note_exists(store, "deploy") is True


# --- list -------------------------------------------------------------------


def test_list_notes_is_sorted_and_skips_dotfiles(tmp_path: Path) -> None:
    store = tmp_path / "scope"
    _write(store, "zeta", "z")
    _write(store, "alpha", "a")
    # The atomic writer parks temp files alongside the real ones, and pathlib
    # globs match dot-prefixed names (unlike the shell), so they must be skipped.
    (notes_dir(store) / ".alpha.md.1234.tmp").write_text("partial", encoding="utf-8")

    assert [d.slug for d in list_notes(store)] == ["alpha", "zeta"]


def test_list_notes_on_an_untouched_scope_is_empty(tmp_path: Path) -> None:
    assert list_notes(tmp_path / "never-written") == []


def test_list_notes_ignores_the_hidden_archive(tmp_path: Path) -> None:
    """``.history/`` is a sibling of ``notes/``, so a replaced revision can
    never come back as a second entry in the lane."""
    store = tmp_path / "scope"
    _write(store, "alpha", "first", now=_T0)
    _write(store, "alpha", "second", now=_T1)

    assert [d.slug for d in list_notes(store)] == ["alpha"]
    assert list(history_dir(store).glob("*.md"))


# --- the archive ------------------------------------------------------------


def test_overwrite_archives_the_prior_revision_with_the_old_text(tmp_path: Path) -> None:
    store = tmp_path / "scope"
    _write(store, "alpha", "ORIGINAL_SENTINEL", now=_T0)
    _write(store, "alpha", "REWRITTEN_SENTINEL", now=_T1)

    live = note_path(store, "alpha").read_text(encoding="utf-8")
    assert "REWRITTEN_SENTINEL" in live
    assert "ORIGINAL_SENTINEL" not in live

    archived = list(history_dir(store).glob("alpha-*.md"))
    assert len(archived) == 1
    assert "ORIGINAL_SENTINEL" in archived[0].read_text(encoding="utf-8")


def test_creating_a_new_note_archives_nothing(tmp_path: Path) -> None:
    store = tmp_path / "scope"
    _write(store, "alpha", "first")
    assert not history_dir(store).exists()


def test_the_archive_lands_before_the_new_content_does(tmp_path: Path, monkeypatch) -> None:
    """Ordering, not just presence: if the new bytes fail to land, the prior
    revision must ALREADY be in ``.history/``. Otherwise a crash mid-rewrite
    would lose the only copy of the text."""
    store = tmp_path / "scope"
    _write(store, "alpha", "ORIGINAL_SENTINEL", now=_T0)

    real_write = knowledge_fs.atomic_write_text
    target = note_path(store, "alpha")

    def failing_write(path: Path, text: str, **kw: object) -> None:
        if path == target:
            raise OSError("disk full")
        real_write(path, text, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(note_files, "atomic_write_text", failing_write)
    with pytest.raises(OSError, match="disk full"):
        _write(store, "alpha", "REWRITTEN_SENTINEL", now=_T1)

    archived = list(history_dir(store).glob("alpha-*.md"))
    assert len(archived) == 1
    assert "ORIGINAL_SENTINEL" in archived[0].read_text(encoding="utf-8")


def test_a_failed_archive_aborts_the_write_and_keeps_the_old_note(
    tmp_path: Path, monkeypatch
) -> None:
    """The archive is not best-effort. If it cannot be made, the rewrite must
    not proceed — the old note stays on disk rather than being replaced by text
    nothing can be recovered from."""
    store = tmp_path / "scope"
    _write(store, "alpha", "ORIGINAL_SENTINEL", now=_T0)

    real_write = knowledge_fs.atomic_write_text
    archive_root = history_dir(store)

    def failing_archive(path: Path, text: str, **kw: object) -> None:
        if path.parent == archive_root:
            raise OSError("archive volume unavailable")
        real_write(path, text, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(note_files, "atomic_write_text", failing_archive)
    with pytest.raises(OSError, match="archive volume unavailable"):
        _write(store, "alpha", "REWRITTEN_SENTINEL", now=_T1)

    survived = note_path(store, "alpha").read_text(encoding="utf-8")
    assert "ORIGINAL_SENTINEL" in survived
    assert "REWRITTEN_SENTINEL" not in survived


def test_archive_reads_the_bytes_on_disk_not_the_callers_idea_of_them(tmp_path: Path) -> None:
    """A note the user edited in their own editor is archived as EDITED — the
    archive is taken from the file, so a hand edit is never silently dropped."""
    store = tmp_path / "scope"
    _write(store, "alpha", "written by the agent", now=_T0)
    note_path(store, "alpha").write_text("HAND_EDITED_SENTINEL\n", encoding="utf-8")

    dest = archive_note(store, "alpha", now=_T1)

    assert dest is not None
    assert dest.read_text(encoding="utf-8") == "HAND_EDITED_SENTINEL\n"


def test_archive_removes_the_note_from_the_lane(tmp_path: Path) -> None:
    store = tmp_path / "scope"
    _write(store, "alpha", "content")
    dest = archive_note(store, "alpha", now=_T1)

    assert dest is not None and dest.exists()
    assert not note_path(store, "alpha").exists()
    assert list_notes(store) == []


def test_archiving_twice_in_the_same_second_does_not_collide(tmp_path: Path) -> None:
    """Two passes over one slug within the same UTC second must produce two
    distinct files — a suffix, never an overwrite of the first archive."""
    store = tmp_path / "scope"
    _write(store, "alpha", "REVISION_ONE", now=_T0)
    first = archive_note(store, "alpha", now=_T1)
    _write(store, "alpha", "REVISION_TWO", now=_T0)
    second = archive_note(store, "alpha", now=_T1)  # same stamp

    assert first is not None and second is not None
    assert first != second
    assert first.exists() and second.exists()
    texts = {first.read_text(encoding="utf-8"), second.read_text(encoding="utf-8")}
    assert any("REVISION_ONE" in t for t in texts)
    assert any("REVISION_TWO" in t for t in texts)
    assert second.stem.endswith("-2")


def test_archive_missing_note_returns_none_and_creates_nothing(tmp_path: Path) -> None:
    store = tmp_path / "scope"
    assert archive_note(store, "never-existed", now=_T0) is None
    assert not history_dir(store).exists()


@pytest.mark.parametrize("slug", ["../evil", "a/b", "..", "", "."])
def test_a_traversing_slug_raises_everywhere(tmp_path: Path, slug: str) -> None:
    """No lane operation may be talked into a path outside ``notes/``."""
    store = tmp_path / "scope"
    with pytest.raises(ValueError):
        archive_note(store, slug, now=_T0)
    with pytest.raises(ValueError):
        write_note(store, slug, title="t", summary="s", body="b", now=_T0)
    with pytest.raises(ValueError):
        read_note(store, slug)
    with pytest.raises(ValueError):
        delete_note(store, slug)


def test_naive_timestamps_are_archived_as_utc(tmp_path: Path) -> None:
    """The archive filename claims to be a UTC stamp, so a naive datetime is
    read as UTC rather than as local time."""
    store = tmp_path / "scope"
    _write(store, "alpha", "one", now=_T0)
    dest = archive_note(store, "alpha", now=datetime(2026, 9, 11, 13, 30, 0))

    assert dest is not None
    assert dest.stem == "alpha-20260911T133000"


# --- delete -----------------------------------------------------------------


def test_delete_archives_rather_than_destroys(tmp_path: Path) -> None:
    """A delete leaves the same recoverable trail as a rewrite: an over-eager
    tidy pass (or a mistaken ``coffer__delete``) is always undoable."""
    store = tmp_path / "scope"
    _write(store, "alpha", "DELETED_SENTINEL")

    assert delete_note(store, "alpha") is True
    assert not note_path(store, "alpha").exists()

    archived = list(history_dir(store).glob("alpha-*.md"))
    assert len(archived) == 1
    assert "DELETED_SENTINEL" in archived[0].read_text(encoding="utf-8")


def test_delete_missing_note_is_false(tmp_path: Path) -> None:
    assert delete_note(tmp_path / "scope", "never-existed") is False
