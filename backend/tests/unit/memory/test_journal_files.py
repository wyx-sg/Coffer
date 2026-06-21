# backend/tests/unit/memory/test_journal_files.py
"""Unit: on-disk journal (episodic) file I/O + period partition."""

from __future__ import annotations

import pathlib
from datetime import UTC, datetime

from coffer.domain.memory.journal import JournalEntry
from coffer.infrastructure.memory.journal_files import (
    append_entry,
    journal_period,
    read_entries,
)


def test_journal_period_is_year_month() -> None:
    assert journal_period(datetime(2026, 6, 21, 9, 0, tzinfo=UTC)) == "2026-06"


def test_read_missing_returns_empty(tmp_path: pathlib.Path) -> None:
    assert read_entries(tmp_path / "nope.md") == []


def test_append_then_read_roundtrip(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "journal" / "2026-06.md"
    t = datetime(2026, 6, 21, 9, 0, tzinfo=UTC)
    append_entry(path, timestamp=t, body="did X")
    assert read_entries(path) == [JournalEntry(timestamp=t, body="did X")]


def test_append_is_ordered_and_accumulates(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "2026-06.md"
    t1 = datetime(2026, 6, 21, 9, 0, tzinfo=UTC)
    t2 = datetime(2026, 6, 21, 10, 0, tzinfo=UTC)
    append_entry(path, timestamp=t1, body="first")
    append_entry(path, timestamp=t2, body="second")
    got = read_entries(path)
    assert [e.body for e in got] == ["first", "second"]
    assert [e.timestamp for e in got] == [t1, t2]


def test_body_with_markdown_heading_is_not_split(tmp_path: pathlib.Path) -> None:
    # A body containing "## Foo" must NOT be mistaken for a new entry delimiter.
    path = tmp_path / "2026-06.md"
    t = datetime(2026, 6, 21, 9, 0, tzinfo=UTC)
    append_entry(path, timestamp=t, body="line1\n## Foo\nline3")
    got = read_entries(path)
    assert len(got) == 1
    assert got[0].body == "line1\n## Foo\nline3"


def test_append_preserves_surrounding_spaces(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "2026-06.md"
    t = datetime(2026, 6, 21, 9, 0, tzinfo=UTC)
    append_entry(path, timestamp=t, body="  indented body  ")
    got = read_entries(path)
    assert got[0].body == "  indented body  "
