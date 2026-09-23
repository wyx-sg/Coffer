"""Carrying out a plan, in the order that makes every failure survivable.

**Notes first, retirements second.** A retirement whose replacement the
writing stage could not produce is skipped and the note stays: taking a
subject out of the partition and putting nothing back is the one outcome worse
than an unrefreshed note.

**A retirement is two halves and they never come apart** (see "Record
retirements so they stick"). The note's file leaves ``notes/`` and a record
goes into ``RETIRED.md`` in the same loop, because in a store whose sources
live outside it a deletion with no record is undone by the next aggregation.

**Provenance accumulates.** A merge that forgot a note's earlier origins would
erase half of what answers "which of my agents already knows this" (see "Record
provenance and merge by meaning").
"""

from __future__ import annotations

import json

import pytest

from coffer.application.memory import distil_apply as applying
from coffer.application.memory import distil_write as writing
from coffer.application.memory.distil_plan import Plan, Target
from coffer.domain.memory.note import TYPE_PROJECT, TYPE_USER, Note, Origin
from coffer.domain.memory.reader import RawEntry
from coffer.domain.memory.retired import RetiredNote
from coffer.infrastructure.memory import store
from coffer.infrastructure.memory.raw_store import StoredRawEntry, list_raw_entries, write_raw_entry
from tests.unit.memory.conftest import ScriptedCompletion

_PARTITION = "coffer"


def _entry(anchor: str, *, agent: str = "codex", terms: tuple[str, ...] = ()) -> StoredRawEntry:
    stored = StoredRawEntry(
        partition=_PARTITION,
        agent=agent,
        native_path=f"/native/{agent}.md",
        captured_at="2026-01-01",
        entry=RawEntry(
            title=f"entry {anchor}",
            description="a description",
            type=TYPE_PROJECT,
            body="the agent's own words",
            anchor=anchor,
            project_root="/home/dev/coffer",
            search_terms=terms,
        ),
    )
    write_raw_entry(stored)
    return stored


def _existing(slug: str = "worktree-trap") -> Note:
    note = Note(
        slug=slug,
        title="Worktree trap",
        description="the conclusion so far",
        type=TYPE_PROJECT,
        body="what the note already says",
        partition=_PARTITION,
        origins=(Origin(agent="claude-code", native_path="/old.md", anchor="x"),),
        created_at="2025-01-01T00:00:00+00:00",
        updated_at="2025-01-01T00:00:00+00:00",
        search_terms=("worktree",),
    )
    store.write_note(note)
    return note


def _written(title: str = "T", description: str = "d", body: str = "Coffer's own prose.") -> str:
    return json.dumps({"title": title, "description": description, "body": body})


async def _carry_out(plan: Plan, answers: list[str], *, retired: list[RetiredNote] | None = None):  # type: ignore[no-untyped-def]
    completion = ScriptedCompletion(answers)
    counts = await applying.carry_out(
        _PARTITION,
        plan,
        retired=retired or [],
        model="a-model",
        completion=completion,  # type: ignore[arg-type]
        credential_resolver=lambda ref: ref,
    )
    return counts, completion


# --- assembling one note -----------------------------------------------------


def test_a_merge_accumulates_provenance_and_moves_only_updated_at() -> None:
    existing = _existing()
    target = Target(
        slug="worktree-trap",
        existing=existing,
        title_hint="Worktree trap",
        type=TYPE_PROJECT,
        entries=[_entry("new", agent="codex", terms=("venv",))],
    )

    note = applying.assemble(target, writing.WrittenNote("T", "d", "b"), _PARTITION)

    assert {o.agent for o in note.origins} == {"claude-code", "codex"}
    assert note.created_at == existing.created_at
    assert note.updated_at > existing.updated_at
    assert note.search_terms == ("worktree", "venv")


def test_re_routing_the_same_entry_does_not_duplicate_its_origin() -> None:
    entry = _entry("one")
    existing = Note(
        slug="n",
        title="N",
        description="d",
        type=TYPE_PROJECT,
        body="b",
        partition=_PARTITION,
        origins=(entry.origin,),
    )
    target = Target(slug="n", existing=existing, title_hint="N", type=TYPE_PROJECT, entries=[entry])

    note = applying.assemble(target, writing.WrittenNote("T", "d", "b"), _PARTITION)

    assert len(note.origins) == 1


def test_a_model_may_set_three_fields_and_no_more() -> None:
    """A model that could set the rest could rename a file, re-file a note
    into ``global``, or drop a provenance entry — none of which is a judgement
    about meaning."""
    target = Target(
        slug="the-slug", existing=None, title_hint="hint", type=TYPE_USER, entries=[_entry("one")]
    )

    note = applying.assemble(target, writing.WrittenNote("Title", "Desc", "Body"), _PARTITION)

    assert (note.slug, note.type, note.partition) == ("the-slug", TYPE_USER, _PARTITION)
    assert (note.title, note.description, note.body) == ("Title", "Desc", "Body")


# --- carrying the plan out ---------------------------------------------------


@pytest.mark.asyncio
async def test_an_opened_note_is_written_and_counted() -> None:
    plan = Plan(
        targets={
            "new-note": Target(
                slug="new-note",
                existing=None,
                title_hint="New note",
                type=TYPE_PROJECT,
                entries=[_entry("one")],
            )
        }
    )

    counts, _ = await _carry_out(plan, [_written(title="New note")])

    assert (counts.opened, counts.merged) == (1, 0)
    assert store.read_note(_PARTITION, "new-note").title == "New note"


@pytest.mark.asyncio
async def test_a_merge_counts_the_entries_it_folded_in() -> None:
    existing = _existing()
    plan = Plan(
        targets={
            "worktree-trap": Target(
                slug="worktree-trap",
                existing=existing,
                title_hint="Worktree trap",
                type=TYPE_PROJECT,
                entries=[_entry("one"), _entry("two")],
            )
        }
    )

    counts, _ = await _carry_out(plan, [_written()])

    assert (counts.opened, counts.merged) == (0, 2)
    assert len(store.read_note(_PARTITION, "worktree-trap").origins) == 3


@pytest.mark.asyncio
async def test_a_note_the_writing_stage_could_not_produce_is_left_alone() -> None:
    """Degrades to nothing (see "Record what each distil pass did"): the
    entries routed there are still in ``.raw/`` and still unaccounted for, so
    the next pass sees them again."""
    existing = _existing()
    plan = Plan(
        targets={
            "worktree-trap": Target(
                slug="worktree-trap",
                existing=existing,
                title_hint="Worktree trap",
                type=TYPE_PROJECT,
                entries=[_entry("one")],
            )
        }
    )

    counts, _ = await _carry_out(plan, ["not json at all"])

    assert (counts.opened, counts.merged) == (0, 0)
    assert store.read_note(_PARTITION, "worktree-trap") == existing


@pytest.mark.asyncio
async def test_a_retirement_removes_the_file_and_records_it_in_one_step() -> None:
    _existing("old-note")
    entry = _entry("one")
    plan = Plan(
        targets={
            "new-note": Target(
                slug="new-note",
                existing=None,
                title_hint="New note",
                type=TYPE_PROJECT,
                entries=[entry],
            )
        },
        retirements={
            "old-note": RetiredNote(
                slug="old-note",
                title="Old note",
                reason="the mechanism was removed",
                replaced_by="new-note",
                retired_at="2026-09-01",
                entry_ids=("aaaa1111bbbb2222",),
            )
        },
    )

    counts, _ = await _carry_out(plan, [_written()])

    assert counts.retired == 1
    assert [n.slug for n in store.list_notes(_PARTITION)] == ["new-note"]
    (record,) = store.read_retired(_PARTITION)
    assert (record.slug, record.replaced_by) == ("old-note", "new-note")
    assert record.entry_ids == ("aaaa1111bbbb2222",)


@pytest.mark.asyncio
async def test_a_retirement_whose_replacement_was_never_written_is_skipped() -> None:
    """Taking a subject out and putting nothing back is strictly worse than
    not running the pass."""
    existing = _existing("old-note")
    plan = Plan(
        targets={
            "new-note": Target(
                slug="new-note",
                existing=None,
                title_hint="New note",
                type=TYPE_PROJECT,
                entries=[_entry("one")],
            )
        },
        retirements={
            "old-note": RetiredNote(
                slug="old-note", title="Old note", reason="r", replaced_by="new-note"
            )
        },
    )

    counts, _ = await _carry_out(plan, ["not json at all"])

    assert counts.retired == 0
    assert store.read_note(_PARTITION, "old-note") == existing
    assert store.read_retired(_PARTITION) == ()


@pytest.mark.asyncio
async def test_an_entry_the_pass_kept_nothing_from_is_recorded_by_its_id() -> None:
    entry = _entry("one")
    plan = Plan(drops=[(entry, "transient observation")])

    counts, completion = await _carry_out(plan, [])

    assert counts.dropped == 1
    assert completion.calls == []  # a drop costs no model call
    (record,) = store.read_retired(_PARTITION)
    assert record.slug == ""  # no note ever existed, so no file is named
    assert record.entry_ids == (entry.entry_id,)
    assert record.reason.startswith(applying.DROPPED_REASON_PREFIX)
    # Distil stays out of ``.raw/``: the entry itself stays there.
    assert [e.entry_id for e in list_raw_entries(_PARTITION)] == [entry.entry_id]


@pytest.mark.asyncio
async def test_earlier_retirements_go_back_down_with_the_new_ones() -> None:
    """``write_retired`` rewrites the whole file, so a lossy round-trip here is
    a note re-opened on the next pass — the failure "Record retirements so they
    stick" exists to prevent."""
    entry = _entry("one")
    earlier = RetiredNote(slug="ancient", title="Ancient", reason="long gone", retired_at="2025")
    plan = Plan(drops=[(entry, "transient")])

    await _carry_out(plan, [], retired=[earlier])

    records = store.read_retired(_PARTITION)
    assert [r.slug for r in records] == ["ancient", ""]
    assert records[0] == earlier


@pytest.mark.asyncio
async def test_a_plan_that_decided_nothing_writes_no_retirement_record() -> None:
    counts, _ = await _carry_out(Plan(), [])
    assert (counts.opened, counts.merged, counts.retired, counts.dropped) == (0, 0, 0, 0)
    assert store.read_retired(_PARTITION) == ()
