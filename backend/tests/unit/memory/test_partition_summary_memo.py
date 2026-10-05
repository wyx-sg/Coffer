"""``summary_of`` remembers what parsing a partition's files adds up to, against a
fingerprint of those files — so a listing costs a stat each, and any change to a
note, a raw entry or ``RETIRED.md`` is seen at once."""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from coffer.application.memory import partition_row
from coffer.application.memory.aggregate import Placement
from coffer.domain.memory.note import TYPE_PROJECT, Note, Origin
from coffer.domain.memory.reader import RawEntry
from coffer.domain.memory.retired import RetiredNote
from coffer.domain.resource import Resource
from coffer.infrastructure.memory import paths, store
from coffer.infrastructure.memory.raw_store import StoredRawEntry, write_raw_entry

_NAME = "coffer"
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _fresh_memo() -> None:
    partition_row._counted_memo.clear()


def _row() -> Resource:
    return Resource(
        uid="u1",
        kind="memory",
        name=_NAME,
        description=None,
        config={"repository_key": "path:/x", "repository_path": "/x"},
        enabled=True,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _summary():  # type: ignore[no-untyped-def]
    row = _row()
    return partition_row.summary_of(row, partition_row.placement_of(row))


def _note(slug: str, updated: str = "2026-01-02T00:00:00+00:00") -> Note:
    return Note(
        slug=slug,
        title="t",
        description="d",
        type=TYPE_PROJECT,
        body="b\n",
        partition=_NAME,
        origins=(Origin(agent="codex", native_path="/n.md", anchor=slug),),
        created_at="2026-01-01T00:00:00+00:00",
        updated_at=updated,
    )


def _raw(anchor: str, agent: str = "claude-code") -> StoredRawEntry:
    return StoredRawEntry(
        partition=_NAME,
        agent=agent,
        native_path=f"/n/{anchor}.md",
        captured_at="2026-01-01T00:00:00+00:00",
        entry=RawEntry(
            title="t",
            description="d",
            type=TYPE_PROJECT,
            body="b",
            anchor=anchor,
            project_root="/x",
        ),
    )


def _count_parses(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []
    real = partition_row._count
    monkeypatch.setattr(partition_row, "_count", lambda n: (calls.append(1), real(n))[1])
    return calls


def test_second_summary_does_not_reparse(monkeypatch: pytest.MonkeyPatch) -> None:
    store.write_note(_note("a"))
    calls = _count_parses(monkeypatch)

    first, second = _summary(), _summary()

    assert first == second
    assert first.note_count == 1
    assert calls == [1]


def test_a_new_note_is_seen(monkeypatch: pytest.MonkeyPatch) -> None:
    store.write_note(_note("a"))
    assert _summary().note_count == 1

    store.write_note(_note("b"))

    assert _summary().note_count == 2


def test_a_rewritten_note_is_seen() -> None:
    store.write_note(_note("a"))
    assert _summary().updated_at == "2026-01-02T00:00:00+00:00"

    path = paths.note_path(_NAME, "a")
    store.write_note(_note("a", updated="2026-02-02T00:00:00+00:00"))
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))  # same size, newer

    assert _summary().updated_at == "2026-02-02T00:00:00+00:00"


def test_a_new_raw_entry_shows_as_waiting() -> None:
    store.write_note(_note("a"))
    assert _summary().waiting_entries == 0

    write_raw_entry(_raw("fresh", agent="codex"))

    summary = _summary()
    assert summary.waiting_entries == 1
    assert summary.waiting_agents == ("codex",)


def test_retiring_an_entry_clears_it_from_waiting() -> None:
    write_raw_entry(_raw("fresh"))
    summary = _summary()
    assert summary.waiting_entries == 1
    entry_id = next(iter(paths.raw_dir(_NAME).glob("*.md"))).stem

    store.write_retired(
        _NAME,
        [
            RetiredNote(
                slug="gone",
                title="g",
                reason="r",
                replaced_by="",
                retired_at="2026-01-03T00:00:00+00:00",
                entry_ids=(entry_id,),
            )
        ],
    )

    assert _summary().waiting_entries == 0


def test_memo_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(partition_row, "_COUNTED_MEMO_MAX", 2)
    for n in ("p1", "p2", "p3"):
        partition_row._counted(n)

    assert len(partition_row._counted_memo) == 2
    assert "p1" not in partition_row._counted_memo


def test_placement_is_untouched() -> None:
    assert partition_row.summary_of(
        _row(), Placement(name=_NAME, repository_key="k", repository_path="/nope")
    ).unresolvable
