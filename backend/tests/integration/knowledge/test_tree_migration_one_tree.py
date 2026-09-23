"""Migration 0101's on-disk rewrite, against a real tree.

See spec knowledge "Migrate the two-lane corpus into the inbox".

0101 retires the two lanes 0085 introduced. Every Markdown file in ``topics/``
and ``sources/`` is queued as material in the collection's hidden ``.inbox/``
for the curation sweep to distil again into one tree of documents, anything
that is not Markdown is left to the backup, and both lanes are removed. The
backup of the whole root comes first, because this pass deletes the originals
outright.

As with 0085, the assertions are about the FILES rather than the report: a
fixture tree in the shape a 0085-era vault actually has, the pass run over it,
and the directory walked to see where everything landed.

``COFFER_KNOWLEDGE_ROOT`` is pinned into ``tmp_path`` by every test here — the
pass moves and deletes, so a test that reached the real ``~/.coffer`` would
destroy the developer's corpus.
"""

from __future__ import annotations

import os
import pathlib

import pytest

from coffer.infrastructure.persistence.migrations import knowledge_tree_0101 as tree


def _write(path: pathlib.Path, text: str, *, mtime: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


@pytest.fixture
def root(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """A knowledge root in the 0085 two-lane shape, with every case in one tree."""
    root = tmp_path / "knowledge"
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(root))

    collection = root / "shopee"
    _write(collection / "README.md", "# shopee\n\nInternal knowledge.\n")
    # Sources written out of mtime order on purpose: the queue follows mtime,
    # not the name a directory listing happens to sort by.
    _write(collection / "sources" / "b-newer.md", "newer source\n", mtime=2_000_000_000)
    _write(collection / "sources" / "a-older.md", "older source\n", mtime=1_000_000_000)
    _write(collection / "sources" / "nested" / "deep.md", "nested source\n", mtime=1_500_000_000)
    # An upload's original bytes, beside the text extracted from it.
    _write(collection / "sources" / "handbook.pdf", "%PDF-fake")
    # A README inside a lane is a blurb about that folder, not material.
    _write(collection / "sources" / "README.md", "about the sources folder\n")
    _write(collection / "topics" / "session-cache.md", "---\ntitle: Session cache\n---\n\ntopic\n")

    # A collection already in the new shape: nothing to rewrite there.
    _write(root / "coffer" / "README.md", "# coffer\n\nThe project's own notes.\n")
    _write(root / "coffer" / "notes.md", "a document\n")
    return root


def _inbox(root: pathlib.Path, collection: str = "shopee") -> list[pathlib.Path]:
    """The inbox in the order the sweep drains it: oldest mtime first."""
    inbox = root / collection / ".inbox"
    return sorted(inbox.iterdir(), key=lambda p: p.stat().st_mtime)


def _tree(root: pathlib.Path) -> set[str]:
    return {str(p.relative_to(root).as_posix()) for p in root.rglob("*")}


@pytest.mark.acceptance(
    spec="knowledge", scenario="migration queues both lanes for re-curation after a backup"
)
def test_both_lanes_are_queued_in_the_inbox_and_removed(root: pathlib.Path) -> None:
    report = tree.migrate()

    queued = {p.read_text(encoding="utf-8") for p in _inbox(root)}
    assert queued == {
        "---\ntitle: Session cache\n---\n\ntopic\n",
        "older source\n",
        "nested source\n",
        "newer source\n",
    }
    assert report.queued == 4
    # The lanes are gone; the collection's own README stays where it was.
    assert not (root / "shopee" / "sources").exists()
    assert not (root / "shopee" / "topics").exists()
    assert (root / "shopee" / "README.md").read_text().startswith("# shopee")
    # Nothing is promoted by the migration itself — that is the sweep's job.
    assert [p.name for p in (root / "shopee").iterdir() if p.is_file()] == ["README.md"]
    assert report.collections == {"shopee"}


def test_topics_are_queued_before_sources_and_sources_by_mtime(root: pathlib.Path) -> None:
    """Topics first, so the first passes lay down a structure by subject; then
    the sources in the order they were written."""
    tree.migrate()

    order = [p.read_text(encoding="utf-8") for p in _inbox(root)]
    assert order[0].endswith("topic\n")
    assert order[1:] == ["older source\n", "nested source\n", "newer source\n"]


def test_item_names_say_which_lane_they_came_from(root: pathlib.Path) -> None:
    tree.migrate()

    names = {p.name for p in _inbox(root)}
    assert names == {
        "topics-session-cache.md",
        "sources-a-older.md",
        "sources-b-newer.md",
        "sources-nested-deep.md",
    }


def test_non_markdown_is_dropped_and_survives_only_in_the_backup(root: pathlib.Path) -> None:
    report = tree.migrate()

    assert report.dropped == 2  # the PDF and the lane README
    assert not any(p.name == "handbook.pdf" for p in root.rglob("*"))
    backup = root.parent / f"knowledge{tree.BACKUP_SUFFIX}"
    assert (backup / "shopee" / "sources" / "handbook.pdf").read_text() == "%PDF-fake"


def test_the_root_is_backed_up_before_anything_moves(root: pathlib.Path) -> None:
    report = tree.migrate()

    backup = root.parent / f"knowledge{tree.BACKUP_SUFFIX}"
    assert report.backup == str(backup)
    # The backup is the tree as it was — both lanes, every file in them.
    assert (backup / "shopee" / "topics" / "session-cache.md").is_file()
    assert (backup / "shopee" / "sources" / "a-older.md").read_text() == "older source\n"
    assert (backup / "shopee" / "sources" / "nested" / "deep.md").is_file()
    assert not (backup / "shopee" / ".inbox").exists()


def test_running_twice_changes_nothing(root: pathlib.Path) -> None:
    tree.migrate()
    after_first = _tree(root)
    contents = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    backup = root.parent / f"knowledge{tree.BACKUP_SUFFIX}"
    backup_before = _tree(backup)

    second = tree.migrate()

    assert _tree(root) == after_first
    assert {p: p.read_bytes() for p in root.rglob("*") if p.is_file()} == contents
    assert second.queued == 0
    assert second.backup == ""
    # And no second backup over the first: the only pre-migration copy stays.
    assert _tree(backup) == backup_before


def test_a_collection_already_in_one_tree_is_left_alone(root: pathlib.Path) -> None:
    tree.migrate()

    assert (root / "coffer" / "notes.md").read_text() == "a document\n"
    assert not (root / "coffer" / ".inbox").exists()


def test_a_colliding_inbox_item_is_suffixed_not_written_over(root: pathlib.Path) -> None:
    """Material already waiting keeps its name; the migrated file takes a suffix."""
    _write(root / "shopee" / ".inbox" / "topics-session-cache.md", "already waiting\n")

    tree.migrate()

    inbox = root / "shopee" / ".inbox"
    assert (inbox / "topics-session-cache.md").read_text() == "already waiting\n"
    assert (inbox / "topics-session-cache-2.md").read_text().endswith("topic\n")


def test_no_backup_is_taken_when_there_is_nothing_to_rewrite(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "knowledge"
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(root))
    _write(root / "coffer" / "README.md", "# coffer\n")
    _write(root / "coffer" / "notes.md", "a document\n")

    report = tree.migrate()

    assert report.backup == ""
    assert report.queued == 0
    assert not (root.parent / f"knowledge{tree.BACKUP_SUFFIX}").exists()
