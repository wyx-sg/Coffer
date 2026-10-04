"""The distil pass, and the two rules that hold on **every** path.

``MEMORY.md`` is always written — even when nothing changed — because the index *is* the delivery
(see "Deliver the index and
the notes path at session start"), and a partition with notes and no index
delivers nothing.

``.raw/`` is never written here (see "Leave the raw directory to aggregation").
The pass reads entries and writes ``notes/``, ``MEMORY.md`` and ``RETIRED.md``;
that separation is what lets a bad distillation be re-run without going back to
the agents, so it is asserted by comparing the bytes **and** the modification
times of every file under ``.raw/`` across a pass.

The pass is mechanical (see "Distil each raw entry into a note mechanically"): it
is handed nothing to call a model with, so "no model is called" is a structural
fact rather than a hopeful one.
"""

from __future__ import annotations

import pytest

from coffer.application.memory.distil import distil_partition, undistilled
from coffer.domain.memory.note import TYPE_PROJECT, TYPE_USER, Note
from coffer.domain.memory.reader import RawEntry
from coffer.domain.memory.retired import RetiredNote
from coffer.infrastructure.memory import paths, store
from coffer.infrastructure.memory.raw_store import StoredRawEntry, list_raw_entries, write_raw_entry

_PARTITION = "coffer"


def _entry(
    title: str,
    body: str,
    *,
    anchor: str = "",
    agent: str = "codex",
    type: str = TYPE_PROJECT,
    search_terms: tuple[str, ...] = (),
) -> StoredRawEntry:
    stored = StoredRawEntry(
        partition=_PARTITION,
        agent=agent,
        native_path=f"/native/{agent}.md",
        captured_at="2026-01-01T00:00:00+00:00",
        entry=RawEntry(
            title=title,
            description=body,
            type=type,
            body=body,
            anchor=anchor or title,
            project_root="/home/dev/coffer",
            search_terms=search_terms,
        ),
    )
    write_raw_entry(stored)
    return stored


def _snapshot_raw() -> dict[str, tuple[bytes, float]]:
    directory = paths.raw_dir(_PARTITION)
    return {str(p): (p.read_bytes(), p.stat().st_mtime) for p in sorted(directory.iterdir())}


async def _mechanical(**kw: object):  # type: ignore[no-untyped-def]
    return await distil_partition(
        _PARTITION, repository_path=str(kw.pop("repository_path", "/home/dev/coffer"))
    )


# --- each entry becomes a note -----------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="distil turns each raw entry into a note and writes the index"
)
async def test_each_entry_becomes_a_note_of_its_own() -> None:
    _entry("Worktree trap", "Worktrees have no .venv.", search_terms=("venv",))
    _entry("Daemon restart", "coffer daemon stop/start.", anchor="two")

    result = await _mechanical()

    assert (result.opened, result.retired) == (2, 0)
    notes = store.list_notes(_PARTITION)
    assert {n.title for n in notes} == {"Worktree trap", "Daemon restart"}
    assert {n.body for n in notes} == {"Worktrees have no .venv.", "coffer daemon stop/start."}
    # The source's own search terms survive the mechanical path too.
    assert next(n for n in notes if n.title == "Worktree trap").search_terms == ("venv",)


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="distil turns each raw entry into a note and writes the index"
)
async def test_the_index_is_written_from_the_notes_frontmatter() -> None:
    _entry("Worktree trap", "Worktrees have no .venv.")

    await _mechanical()

    index = store.read_index(_PARTITION)
    assert "# coffer — Coffer memory" in index
    assert "`/home/dev/coffer`" in index
    assert "- **Worktree trap** (`worktree-trap.md`)" in index


@pytest.mark.asyncio
async def test_the_pass_merges_nothing_and_retires_nothing_by_meaning() -> None:
    """Both are judgements about meaning, and nothing mechanical can make
    them — so the partition is thinner, not wrong."""
    _entry("One telling", "The worktree has no .venv.", agent="codex")
    _entry("Another telling", "A linked checkout fails to build.", agent="claude-code", anchor="b")

    result = await _mechanical()

    assert len(store.list_notes(_PARTITION)) == 2
    assert store.read_retired(_PARTITION) == ()
    assert result.retired == 0


@pytest.mark.asyncio
async def test_two_entries_with_one_title_get_two_files() -> None:
    _entry("Same title", "first body", anchor="one")
    _entry("Same title", "second body", anchor="two")

    await _mechanical()

    assert sorted(n.slug for n in store.list_notes(_PARTITION)) == ["same-title", "same-title-2"]


@pytest.mark.asyncio
async def test_a_new_note_never_reuses_the_file_name_of_a_retired_one() -> None:
    """Reusing it would make ``RETIRED.md`` read as though a live note had
    been removed."""
    store.write_retired(
        _PARTITION, [RetiredNote(slug="worktree-trap", title="Worktree trap", reason="stale")]
    )
    _entry("Worktree trap", "a fresh telling")

    await _mechanical()

    assert [n.slug for n in store.list_notes(_PARTITION)] == ["worktree-trap-2"]


# --- ``.raw/`` is aggregation's alone ----------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="raw entries land hidden, and only aggregation writes them"
)
@pytest.mark.acceptance(
    spec="memory", scenario="leave the raw directory byte-identical through a distil pass"
)
async def test_a_distil_pass_leaves_every_raw_entry_byte_identical() -> None:
    _entry("Worktree trap", "Worktrees have no .venv.")
    _entry("Daemon restart", "coffer daemon stop/start.", anchor="two")
    before = _snapshot_raw()
    assert before

    await _mechanical()

    assert _snapshot_raw() == before
    assert len(list_raw_entries(_PARTITION)) == 2


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="raw entries land hidden, and only aggregation writes them"
)
async def test_raw_entries_are_excluded_from_the_index_the_pass_writes() -> None:
    stored = _entry("Worktree trap", "Worktrees have no .venv.")

    await _mechanical()

    index = store.read_index(_PARTITION)
    assert ".raw" not in index
    assert stored.entry_id not in index


# --- what a pass considers new -----------------------------------------------


def test_an_entry_named_in_a_notes_provenance_is_not_offered_again() -> None:
    stored = _entry("Worktree trap", "Worktrees have no .venv.")
    note = Note(
        slug="worktree-trap",
        title="Worktree trap",
        description="d",
        type=TYPE_PROJECT,
        body="b",
        partition=_PARTITION,
        origins=(stored.origin,),
    )

    assert undistilled(_PARTITION, [note], []) == ()
    assert [e.entry_id for e in undistilled(_PARTITION, [], [])] == [stored.entry_id]


def test_an_entry_a_pass_kept_nothing_from_is_not_offered_again() -> None:
    """``.raw/`` may not be pruned to express a drop (see "Leave the raw directory to
    aggregation"), so without the record the same entry is routed to the
    model on every pass for the rest of the vault's life."""
    stored = _entry("Transient", "an incidental observation")
    record = RetiredNote(
        slug="", title="Transient", reason="kept nothing", entry_ids=(stored.entry_id,)
    )

    assert undistilled(_PARTITION, [], [record]) == ()


def test_a_retired_notes_own_entries_are_accounted_for_the_moment_it_leaves() -> None:
    """The record carries the entries the note was built from, so they do not
    resurface as undistilled — and get re-charged to a model — a pass later."""
    stored = _entry("The old mechanism", "it shipped")
    record = RetiredNote(
        slug="the-old-mechanism",
        title="The old mechanism",
        reason="removed in the rewrite",
        replaced_by="the-new-mechanism",
        entry_ids=(stored.entry_id,),
    )

    assert undistilled(_PARTITION, [], [record]) == ()


def test_undistilled_reads_raw_and_writes_nothing() -> None:
    _entry("A", "b")
    before = _snapshot_raw()

    undistilled(_PARTITION, [], [])

    assert _snapshot_raw() == before
    assert store.list_notes(_PARTITION) == ()


# --- the index is written on every path --------------------------------------


@pytest.mark.asyncio
async def test_a_pass_with_no_new_entries_still_rewrites_the_index() -> None:
    standing = _entry("Standing", "b", anchor="x")
    store.write_note(
        Note(
            slug="standing",
            title="Standing",
            description="from an earlier pass",
            type=TYPE_USER,
            body="b",
            partition=_PARTITION,
            origins=(standing.origin,),
        )
    )

    result = await _mechanical()

    assert result.opened == 0
    assert "- **Standing** (`standing.md`)" in store.read_index(_PARTITION)


@pytest.mark.asyncio
async def test_an_empty_partition_gets_an_index_saying_so() -> None:
    await _mechanical()
    assert "No notes yet." in store.read_index(_PARTITION)


# --- notes an agent marked retired -------------------------------------------


def _note_from(stored: StoredRawEntry, slug: str, **marks: str) -> Note:
    note = Note(
        slug=slug,
        title=slug.replace("-", " ").capitalize(),
        description=f"About {slug}.",
        type=TYPE_PROJECT,
        body=f"{slug} body.",
        partition=_PARTITION,
        origins=(stored.origin,),
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        **marks,
    )
    store.write_note(note)
    return note


def test_a_retired_marker_survives_a_write_and_a_read() -> None:
    stored = _entry("Old", "body")
    _note_from(stored, "old", retired="superseded", replaced_by="new")

    note = store.read_note(_PARTITION, "old")

    assert (note.retired, note.replaced_by) == ("superseded", "new")


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="an agent-retired note is recorded with its entry ids and not recreated"
)
async def test_a_marked_note_is_retired_with_its_entry_ids_and_not_recreated() -> None:
    stored = _entry("Old", "body")
    _note_from(stored, "old", retired="superseded by the lockfile note", replaced_by="lockfile")

    first = await _mechanical()

    assert first.retired == 1 and first.opened == 0
    assert store.list_notes(_PARTITION) == ()
    (record,) = store.read_retired(_PARTITION)
    assert record.slug == "old" and record.title == "Old"
    assert record.reason == "superseded by the lockfile note"
    assert record.replaced_by == "lockfile"
    assert record.entry_ids == (stored.entry_id,)
    assert "old.md" not in store.read_index(_PARTITION)

    second = await _mechanical()

    assert (second.opened, second.retired) == (0, 0)
    assert store.list_notes(_PARTITION) == ()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="a retired mark without a replacement is recorded without one"
)
async def test_a_mark_without_a_replacement_is_recorded_without_one() -> None:
    stored = _entry("Old", "body")
    _note_from(stored, "old", retired="the service was removed")

    await _mechanical()

    (record,) = store.read_retired(_PARTITION)
    assert (record.reason, record.replaced_by) == ("the service was removed", "")


@pytest.mark.asyncio
async def test_a_merge_by_appending_origins_and_deleting_the_file_recreates_nothing() -> None:
    first = _entry("First", "one", anchor="a")
    second = _entry("Second", "two", anchor="b")
    survivor = _note_from(first, "first")
    store.write_note(
        Note(**{**survivor.__dict__, "origins": (first.origin, second.origin)})  # type: ignore[arg-type]
    )
    _note_from(second, "second")
    store.delete_note(_PARTITION, "second")

    result = await _mechanical()

    assert (result.opened, result.retired) == (0, 0)
    assert [n.slug for n in store.list_notes(_PARTITION)] == ["first"]
    assert store.read_retired(_PARTITION) == ()
