"""A partition's four files, and the one-writer-per-directory split (see "Keep
distil out of the raw directory").

``COFFER_MEMORY_ROOT`` is pinned to ``tmp_path`` by the suite-wide
``_isolated_memory_root`` fixture (``backend/tests/conftest.py``), so every
test here writes real files under a throwaway directory — never a developer's
real ``~/.coffer/memory``.

This file covers the three ``store.py`` owns — ``notes/``, ``RETIRED.md`` and
``MEMORY.md``. ``.raw/`` is a module of its own (``raw_store.py``) and is
tested in ``test_raw_store.py``, which is the split that makes "Keep distil out
of the raw directory" checkable by reading an import list: the one directory
only aggregation may write is the one module only aggregation imports.

What this file is really about is that **``RETIRED.md`` round-trips
losslessly** (see "Record retirements so they stick"). It is the next pass's
exclusion list, so a record that comes back short is a note re-opened on every
pass thereafter — including when a reason contains a horizontal rule, which
PyYAML writes as an indented continuation.
"""

from __future__ import annotations

import pytest

from coffer.domain.memory.note import TYPE_FEEDBACK, TYPE_PROJECT, Note, Origin
from coffer.domain.memory.reader import RawEntry
from coffer.domain.memory.retired import RetiredNote
from coffer.infrastructure.memory import paths, store
from coffer.infrastructure.memory.raw_store import StoredRawEntry, write_raw_entry
from coffer.infrastructure.memory.store import NoteNotFound

_PARTITION = "coffer"


def _note(slug: str, *, title: str = "A note", type: str = TYPE_PROJECT, **kw: object) -> Note:
    return Note(
        slug=slug,
        title=title,
        description=kw.pop("description", "one line that answers it"),  # type: ignore[arg-type]
        type=type,
        body=kw.pop("body", "Coffer's own prose.\n"),  # type: ignore[arg-type]
        partition=_PARTITION,
        origins=kw.pop("origins", (Origin(agent="codex", native_path="/n.md", anchor="a"),)),  # type: ignore[arg-type]
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-02T00:00:00+00:00",
        search_terms=kw.pop("search_terms", ()),  # type: ignore[arg-type]
    )


# --- notes -------------------------------------------------------------------


def test_a_note_round_trips_with_its_provenance_and_search_terms() -> None:
    origins = (
        Origin(agent="claude-code", native_path="/a.md", anchor="x", captured_at="2026-01-01"),
        Origin(agent="codex", native_path="/b.md", anchor="y", source_written_at="2025-12-01"),
    )
    written = _note("worktree-development", origins=origins, search_terms=("worktree", "venv"))

    relative = store.write_note(written)

    assert relative == "coffer/notes/worktree-development.md"
    back = store.read_note(_PARTITION, "worktree-development")
    assert back == written


def test_a_notes_provenance_names_every_contributing_agent() -> None:
    store.write_note(
        _note(
            "shared",
            origins=(
                Origin(agent="claude-code", native_path="/a.md", anchor="x"),
                Origin(agent="codex", native_path="/b.md", anchor="y"),
            ),
        )
    )
    assert store.read_note(_PARTITION, "shared").agents == ("claude-code", "codex")


def test_reading_a_note_that_is_not_there_names_the_partition_and_slug() -> None:
    with pytest.raises(NoteNotFound) as caught:
        store.read_note(_PARTITION, "never-written")
    assert caught.value.partition == _PARTITION
    assert caught.value.slug == "never-written"
    assert caught.value.code == "MEMORY_NOTE_NOT_FOUND"


def test_notes_are_listed_by_slug_not_by_timestamp() -> None:
    """One definition of "newest" lives in the index renderer (see "Write each
    index line to stand on its own"); a second ordering here is how the file
    and the delivery drifted apart."""
    store.write_note(_note("zebra"))
    store.write_note(_note("alpha"))
    assert [n.slug for n in store.list_notes(_PARTITION)] == ["alpha", "zebra"]


def test_listing_notes_of_a_partition_with_none_is_empty() -> None:
    assert store.list_notes("never-created") == ()


def test_deleting_a_note_reports_whether_there_was_one() -> None:
    store.write_note(_note("doomed"))
    assert store.delete_note(_PARTITION, "doomed") is True
    assert store.delete_note(_PARTITION, "doomed") is False
    assert store.list_notes(_PARTITION) == ()


def test_a_note_keeps_its_identity_when_it_gains_an_origin() -> None:
    """A note's key is the smallest of its origin keys, so a merge does not
    silently move a reference off the note it was written about."""
    first = Origin(agent="codex", native_path="/b.md", anchor="y")
    second = Origin(agent="claude-code", native_path="/a.md", anchor="x")
    one = _note("n", origins=(first,))
    two = _note("n", origins=(first, second))
    assert two.key == min(first.key, second.key)
    assert one.key in {first.key}


# --- the retirement record ---------------------------------------------------


def test_the_retirement_record_round_trips_every_field() -> None:
    record = RetiredNote(
        slug="old-note",
        title="The mechanism shipped",
        reason="It was removed in the September rewrite.",
        replaced_by="new-note",
        retired_at="2026-09-01T00:00:00+00:00",
        entry_ids=("aaaa1111bbbb2222", "cccc3333dddd4444"),
    )
    store.write_retired(_PARTITION, [record])
    assert store.read_retired(_PARTITION) == (record,)


def test_a_reason_containing_a_horizontal_rule_round_trips() -> None:
    """The exclusion list's own trap (see "Record retirements so they stick").

    PyYAML writes this reason as an indented continuation, so the ``---``
    inside it sits at column 4. A reader that ended the frontmatter at the
    first stripped ``---`` would return **no** records — and a partition whose
    exclusion list reads empty re-opens every note it retired, on every pass,
    forever.
    """
    reason = "Shipped, then removed.\n\n---\n\nSee the ADR for why.\n"
    record = RetiredNote(slug="old", title="Old", reason=reason, retired_at="2026-09-01")

    store.write_retired(_PARTITION, [record])

    back = store.read_retired(_PARTITION)
    assert len(back) == 1
    assert back[0].reason == reason
    assert back[0].slug == "old"


def test_the_record_is_written_twice_once_for_each_reader() -> None:
    """Above the fence for the next pass, below it for a human — and the prose
    half is regenerated from the same list, so the two cannot disagree."""
    store.write_retired(
        _PARTITION,
        [RetiredNote(slug="old", title="Old note", reason="no longer true", replaced_by="new")],
    )
    text = paths.retired_path(_PARTITION).read_text(encoding="utf-8")
    assert "## Old note" in text
    assert "was `notes/old.md`" in text
    assert "replaced by `notes/new.md`" in text


def test_a_dropped_entrys_record_names_no_file_that_never_existed() -> None:
    store.write_retired(
        _PARTITION,
        [RetiredNote(slug="", title="Transient", reason="nothing to carry", entry_ids=("abc",))],
    )
    text = paths.retired_path(_PARTITION).read_text(encoding="utf-8")
    assert "never became a note" in text
    assert "notes/.md" not in text
    assert store.read_retired(_PARTITION)[0].entry_ids == ("abc",)


def test_writing_an_empty_record_removes_the_file() -> None:
    store.write_retired(_PARTITION, [RetiredNote(slug="old", title="Old", reason="r")])
    assert paths.retired_path(_PARTITION).is_file()

    store.write_retired(_PARTITION, [])

    assert not paths.retired_path(_PARTITION).exists()
    assert store.read_retired(_PARTITION) == ()


def test_reading_a_partition_with_no_retirement_record_is_empty() -> None:
    assert store.read_retired("never-created") == ()


def test_the_record_keeps_the_order_it_was_written_in() -> None:
    records = [
        RetiredNote(slug="second", title="B", reason="r", retired_at="2026-02-01"),
        RetiredNote(slug="first", title="A", reason="r", retired_at="2026-01-01"),
    ]
    store.write_retired(_PARTITION, records)
    assert [r.slug for r in store.read_retired(_PARTITION)] == ["second", "first"]


# --- the index, and the partition itself -------------------------------------


def test_the_index_is_written_and_read_as_opaque_text() -> None:
    store.write_index(_PARTITION, "# coffer — Coffer memory\n")
    assert store.read_index(_PARTITION) == "# coffer — Coffer memory\n"


def test_reading_the_index_of_a_partition_without_one_is_empty() -> None:
    assert store.read_index("never-created") == ""


def test_partitions_are_the_directories_on_disk_minus_the_layers_own_state() -> None:
    store.write_note(_note("a"))
    store.write_index("global", "index")
    (paths.memory_root() / ".hidden-state").mkdir(parents=True, exist_ok=True)

    assert store.list_partitions() == ("coffer", "global")


def test_listing_partitions_before_anything_is_written_is_empty() -> None:
    assert store.list_partitions() == ()


def test_deleting_a_partition_removes_its_notes_index_and_raw_entries() -> None:
    store.write_note(_note("a", type=TYPE_FEEDBACK))
    store.write_index(_PARTITION, "index")
    write_raw_entry(_raw_entry())
    store.write_retired(_PARTITION, [RetiredNote(slug="x", title="X", reason="r")])

    store.delete_partition(_PARTITION)

    assert not paths.partition_dir(_PARTITION).exists()
    assert store.list_partitions() == ()


def test_deleting_a_partition_that_is_not_there_is_a_no_op() -> None:
    store.delete_partition("never-created")  # does not raise


def _raw_entry() -> StoredRawEntry:
    """One entry under ``.raw/``, only so the partition-delete test can prove
    it takes the hidden directory with it."""
    return StoredRawEntry(
        partition=_PARTITION,
        agent="claude-code",
        native_path="/home/dev/.claude/projects/x/memory/f.md",
        captured_at="2026-01-01T00:00:00+00:00",
        entry=RawEntry(
            title="Use a worktree",
            description="Always develop in a worktree",
            type=TYPE_PROJECT,
            body="the agent's own words",
            anchor="a",
            project_root="/home/dev/coffer",
        ),
    )
