"""``.raw/`` — what was read out of the agents, verbatim (FR-008, FR-009).

Its own module because its own directory: ``raw_store.py`` is the only thing
aggregation writes through, and nothing the distil pass imports. That split is
what makes FR-026 checkable by reading an import list rather than by trusting a
comment, and this file holds the property the split exists for — **a body
comes back exactly as the reader handed it over**, CRLF and trailing
whitespace included. The moment a round-trip rewrites one character, "re-run
the distillation without going back to the agents" stops meaning what it says.

``COFFER_MEMORY_ROOT`` is pinned to ``tmp_path`` by the suite-wide
``_isolated_memory_root`` fixture (``backend/tests/conftest.py``).
"""

from __future__ import annotations

import pytest

from coffer.domain.memory.note import TYPE_PROJECT, origin_key
from coffer.domain.memory.reader import RawEntry
from coffer.infrastructure.memory import paths
from coffer.infrastructure.memory.raw_store import (
    RawEntryNotFound,
    StoredRawEntry,
    delete_raw_entry,
    list_raw_entries,
    read_raw_entry,
    write_raw_entry,
)

_PARTITION = "coffer"


def _stored(
    body: str = "the agent's own words",
    *,
    anchor: str = "a",
    agent: str = "claude-code",
    native_path: str = "/home/dev/.claude/projects/x/memory/f.md",
    title: str = "Use a worktree",
    project_root: str = "/home/dev/coffer",
    search_terms: tuple[str, ...] = (),
) -> StoredRawEntry:
    return StoredRawEntry(
        partition=_PARTITION,
        agent=agent,
        native_path=native_path,
        captured_at="2026-01-01T00:00:00+00:00",
        entry=RawEntry(
            title=title,
            description="Always develop in a worktree",
            type=TYPE_PROJECT,
            body=body,
            anchor=anchor,
            project_root=project_root,
            source_written_at="2025-12-31T00:00:00+00:00",
            search_terms=search_terms,
        ),
    )


def test_a_raw_entry_round_trips_byte_for_byte_including_crlf() -> None:
    body = "first line\r\nsecond line with trailing spaces   \r\n\r\n"
    stored = _stored(body, search_terms=("daemon", "restart"))

    relative = write_raw_entry(stored)

    assert relative == f"coffer/.raw/{stored.entry_id}.md"
    back = read_raw_entry(_PARTITION, stored.entry_id)
    assert back.entry.body == body
    assert back == stored


def test_a_raw_entrys_file_name_is_its_origin_key() -> None:
    """Hashed rather than concatenated: it travels in file names and in
    frontmatter, and an absolute path there leaks the shape of the user's disk
    into a file they read often."""
    stored = _stored(agent="codex", native_path="/n.md", anchor="group::section::abc")

    write_raw_entry(stored)

    assert stored.entry_id == origin_key("codex", "/n.md", "group::section::abc")
    assert paths.raw_path(_PARTITION, stored.entry_id).is_file()
    assert "/n.md" not in paths.raw_path(_PARTITION, stored.entry_id).name


def test_re_reading_an_unchanged_source_overwrites_one_file() -> None:
    """A second pass over the same (agent, file, anchor) must not accumulate a
    near-duplicate (FR-009)."""
    write_raw_entry(_stored("first text"))
    write_raw_entry(_stored("second text"))

    entries = list_raw_entries(_PARTITION)
    assert len(entries) == 1
    assert entries[0].entry.body == "second text"


def test_a_raw_entry_carries_the_agent_path_and_time_it_came_from() -> None:
    stored = _stored(agent="codex", native_path="/home/dev/.codex/memories/MEMORY.md")

    write_raw_entry(stored)

    back = read_raw_entry(_PARTITION, stored.entry_id)
    assert (back.agent, back.native_path, back.captured_at) == (
        "codex",
        "/home/dev/.codex/memories/MEMORY.md",
        "2026-01-01T00:00:00+00:00",
    )
    assert back.entry.project_root == "/home/dev/coffer"
    assert back.entry.source_written_at == "2025-12-31T00:00:00+00:00"


def test_a_stored_entry_names_itself_as_a_notes_provenance_would() -> None:
    stored = _stored(agent="codex", native_path="/n.md", anchor="x")
    origin = stored.origin
    assert (origin.agent, origin.native_path, origin.anchor) == ("codex", "/n.md", "x")
    assert origin.key == stored.entry_id
    assert origin.source_written_at == "2025-12-31T00:00:00+00:00"


def test_reading_a_raw_entry_that_is_not_there_names_it() -> None:
    with pytest.raises(RawEntryNotFound) as caught:
        read_raw_entry(_PARTITION, "deadbeefdeadbeef")
    assert caught.value.partition == _PARTITION
    assert caught.value.entry_id == "deadbeefdeadbeef"
    assert caught.value.code == "MEMORY_RAW_ENTRY_NOT_FOUND"


def test_deleting_a_raw_entry_reports_whether_there_was_one() -> None:
    stored = _stored()
    write_raw_entry(stored)
    assert delete_raw_entry(_PARTITION, stored.entry_id) is True
    assert delete_raw_entry(_PARTITION, stored.entry_id) is False


def test_entries_are_listed_by_id_for_a_stable_ordering() -> None:
    ids = sorted(write_raw_entry(_stored(anchor=a)).split("/")[-1] for a in ("a", "b", "c"))
    assert [f"{e.entry_id}.md" for e in list_raw_entries(_PARTITION)] == ids


def test_listing_raw_entries_of_a_partition_with_none_is_empty() -> None:
    assert list_raw_entries("never-created") == ()


def test_raw_entries_are_hidden_from_the_partitions_ordinary_listing() -> None:
    """``.raw/`` is excluded from the index, from delivery and from recall
    (FR-008) — which starts with it not being a note."""
    from coffer.infrastructure.memory import store

    write_raw_entry(_stored())

    assert store.list_notes(_PARTITION) == ()
    assert paths.raw_dir(_PARTITION).name.startswith(".")
