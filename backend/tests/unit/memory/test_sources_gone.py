"""A note whose raw entries are all gone is retired (see "Retire a note whose raw
entries are all gone").

The case that forced it: a ``feedback`` entry once filed into ``global`` is now
filed into its repository's partition. Aggregation moves the raw entry, but the
note distil had already written into ``global`` stayed — so the same lesson was
served from two partitions. The sweep runs on every pass, the mechanical one
included, and its record excludes nothing: nobody judged the note untrue.
"""

from __future__ import annotations

import dataclasses
import json
import pathlib

import pytest

from coffer.application.memory.distil import SOURCES_GONE_REASON, distil_partition
from coffer.domain.memory.note import TYPE_FEEDBACK, TYPE_PROJECT, Note
from coffer.domain.memory.retired import RetiredNote
from coffer.infrastructure.memory import paths, source_state, store
from coffer.infrastructure.memory.raw_store import (
    StoredRawEntry,
    delete_raw_entry,
    list_raw_entries,
    write_raw_entry,
)
from tests.unit.memory.conftest import (
    ExplodingCompletion,
    FakeAudit,
    FakeReader,
    FakeResources,
    NoModelSelector,
    ScriptedCompletion,
    StubModelSelector,
    memory_service,
    raw_entry,
)


def _repository(tmp_path: pathlib.Path, name: str) -> pathlib.Path:
    root = tmp_path / name
    (root / ".git").mkdir(parents=True)
    return root


async def _mechanical(partition: str):  # type: ignore[no-untyped-def]
    return await distil_partition(
        partition,
        completion=ExplodingCompletion(),  # type: ignore[arg-type]
        model_selector=NoModelSelector(),  # type: ignore[arg-type]
    )


def _stored(partition: str, title: str, *, anchor: str = "") -> StoredRawEntry:
    stored = StoredRawEntry(
        partition=partition,
        agent="codex",
        native_path="/native/codex.md",
        captured_at="2026-01-01T00:00:00+00:00",
        entry=raw_entry(title, f"{title} body.", anchor=anchor or title),
    )
    write_raw_entry(stored)
    return stored


def _note(partition: str, slug: str, *origins: StoredRawEntry) -> Note:
    note = Note(
        slug=slug,
        title=slug.replace("-", " ").capitalize(),
        description=f"About {slug}.",
        type=TYPE_PROJECT,
        body=f"{slug} body.",
        partition=partition,
        origins=tuple(o.origin for o in origins),
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )
    store.write_note(note)
    return note


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="a global note whose entries moved to the project partition is retired"
)
async def test_a_global_feedback_note_leaves_once_aggregation_refiles_its_entry(
    tmp_path: pathlib.Path,
) -> None:
    root = _repository(tmp_path, "coffer")
    resources = FakeResources()
    resources.add_agent("claude-code", "claude_code", "/cc")
    reader = FakeReader(agent_type="claude_code")
    source = "/cc/projects/coffer/memory/f.md"
    entry = raw_entry(
        "Run the gates", "Run make verify.", type=TYPE_FEEDBACK, project_root=str(root)
    )
    reader.set_source("/cc", source, "d1", (entry,))
    service = memory_service(resources, {"claude_code": reader}, audit=FakeAudit())
    await service.aggregate()
    # What the previous filing rule left behind: the entry under global's
    # .raw/, a note distilled from it there, and an unversioned digest cache.
    (stored,) = list_raw_entries("coffer")
    store.delete_partition("coffer")
    write_raw_entry(dataclasses.replace(stored, partition="global"))
    await _mechanical("global")
    assert [n.title for n in store.list_notes("global")] == ["Run the gates"]
    (paths.memory_root() / source_state.STATE_FILENAME).write_text(
        json.dumps({source: "d1"}), encoding="utf-8"
    )

    await service.aggregate()
    global_result = await _mechanical("global")
    await _mechanical("coffer")

    assert list_raw_entries("global") == ()
    assert store.list_notes("global") == ()
    assert "Run the gates" not in store.read_index("global")
    (record,) = store.read_retired("global")
    assert (record.slug, record.title, record.reason) == (
        "run-the-gates",
        "Run the gates",
        SOURCES_GONE_REASON,
    )
    assert record.sources_gone is True and record.entry_ids == ()
    assert global_result.retired == 1
    # The lesson is served from exactly one partition now: the project's.
    assert [n.title for n in store.list_notes("coffer")] == ["Run the gates"]
    assert "Run the gates" in store.read_index("coffer")


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="a sources-gone retirement excludes nothing later")
async def test_a_sources_gone_record_is_not_handed_to_routing_and_its_subject_can_return() -> None:
    kept_a = _stored("coffer", "Keep A")
    kept_b = _stored("coffer", "Keep B")
    gone = _stored("coffer", "Gone")
    _note("coffer", "partial", kept_a, kept_b)
    _note("coffer", "orphan", gone)
    _note("coffer", "unsourced")
    delete_raw_entry("coffer", kept_b.entry_id)
    delete_raw_entry("coffer", gone.entry_id)
    # Keep A is accounted for by "partial", so the first pass has nothing new.
    first = await distil_partition(
        "coffer", completion=ScriptedCompletion([]), model_selector=StubModelSelector()
    )
    assert first.retired == 1
    assert sorted(n.slug for n in store.list_notes("coffer")) == ["partial", "unsourced"]

    returning = _stored("coffer", "Orphan", anchor="returned")
    completion = ScriptedCompletion(
        [
            json.dumps(
                {"actions": [{"entry": returning.entry_id, "action": "open", "title": "Orphan"}]}
            ),
            json.dumps({"title": "Orphan", "description": "Back again.", "body": "Returned."}),
        ]
    )
    second = await distil_partition(
        "coffer", completion=completion, model_selector=StubModelSelector()
    )

    routing_request = json.loads(completion.calls[0]["user"])
    assert routing_request["retired_subjects"] == []
    assert second.opened == 1
    assert "Back again." in store.read_index("coffer")
    partial = store.read_note("coffer", "partial")
    assert [o.key for o in partial.origins] == [kept_a.entry_id, kept_b.entry_id]
    # The earlier record is still there, untouched, beside nothing new.
    assert [r.sources_gone for r in store.read_retired("coffer")] == [True]


@pytest.mark.asyncio
async def test_a_contradiction_retirement_is_still_an_excluded_subject() -> None:
    """Only ``sources_gone`` records are left off routing's exclusion list."""
    store.write_retired(
        "coffer",
        [
            RetiredNote(slug="old", title="Judged untrue", reason="Contradicted."),
            RetiredNote(slug="gone", title="Sourceless", reason="x", sources_gone=True),
        ],
    )
    _stored("coffer", "New entry")
    completion = ScriptedCompletion([])

    await distil_partition("coffer", completion=completion, model_selector=StubModelSelector())

    assert json.loads(completion.calls[0]["user"])["retired_subjects"] == ["Judged untrue"]


def test_sources_gone_round_trips_through_retired_md_and_is_absent_when_unset() -> None:
    store.write_retired(
        "coffer",
        [
            RetiredNote(slug="a", title="A", reason="Contradicted.", entry_ids=("e1",)),
            RetiredNote(slug="b", title="B", reason=SOURCES_GONE_REASON, sources_gone=True),
        ],
    )

    first, second = store.read_retired("coffer")
    text = paths.retired_path("coffer").read_text(encoding="utf-8")

    assert (first.sources_gone, second.sources_gone) == (False, True)
    assert text.count("sources_gone") == 1
    assert "its sources are gone" in text
