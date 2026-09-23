"""Folding routed answers into a plan, and the rules a prompt cannot hold.

Two invariants live here rather than in the prompt, because a model cannot be
relied on to hold them across a chunk boundary and either one broken leaves a
note file contradicting the record of its own removal:

* a note this pass is **writing** is not also **retired**, and one it is
  retiring is not also merged into;
* a chunk that opens a note lets the *next* chunk merge into it, and a chunk
  that retires one does not — which is what makes a partition split across
  several requests behave like one.

Nothing here writes ``.raw/`` (see "Keep distil out of the raw directory"): it
reads the entries the caller listed and produces a plan, which ``distil_apply``
then carries out.
"""

from __future__ import annotations

import json

import pytest

from coffer.application.memory import distil_plan as planning
from coffer.domain.memory.note import TYPE_FEEDBACK, TYPE_PROJECT, TYPE_USER, Note, Origin
from coffer.domain.memory.reader import RawEntry
from coffer.domain.memory.retired import RetiredNote
from coffer.infrastructure.memory.raw_store import StoredRawEntry
from tests.unit.memory.conftest import ScriptedCompletion

_PARTITION = "coffer"


def _entry(anchor: str, *, agent: str = "codex", title: str = "") -> StoredRawEntry:
    return StoredRawEntry(
        partition=_PARTITION,
        agent=agent,
        native_path=f"/native/{agent}.md",
        captured_at="2026-01-01",
        entry=RawEntry(
            title=title or f"entry {anchor}",
            description="a description",
            type=TYPE_PROJECT,
            body="the agent's own words",
            anchor=anchor,
            project_root="/home/dev/coffer",
        ),
    )


def _note(slug: str, *, type: str = TYPE_PROJECT) -> Note:
    return Note(
        slug=slug,
        title=slug.replace("-", " ").title(),
        description="the conclusion",
        type=type,
        body="the existing body",
        partition=_PARTITION,
        origins=(Origin(agent="codex", native_path="/old.md", anchor=slug),),
        created_at="2025-01-01",
        updated_at="2025-01-01",
    )


async def _plan(
    entries: list[StoredRawEntry],
    answers: list[str],
    *,
    notes: list[Note] | None = None,
    retired: list[RetiredNote] | None = None,
    chunk_size: int = 50,
) -> tuple[planning.Plan, ScriptedCompletion]:
    completion = ScriptedCompletion(answers)
    plan = await planning.build_plan(
        _PARTITION,
        entries,
        notes=notes or [],
        retired=retired or [],
        model="a-model",
        completion=completion,  # type: ignore[arg-type]
        credential_resolver=lambda ref: ref,
        chunk_size=chunk_size,
    )
    return plan, completion


def _actions(*items: dict[str, object]) -> str:
    return json.dumps({"actions": list(items)})


# --- the pure helpers --------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Worktree development", "worktree-development"),
        ("  Mixed/Case_Title  ", "mixed-case-title"),
        ("!!!", "note"),
        ("", "note"),
        ("中文标题", "中文标题"),
    ],
)
def test_a_slug_is_readable_and_never_empty(title: str, expected: str) -> None:
    assert planning.unique_slug(title, set()) == expected


def test_a_slug_collides_with_nothing_the_partition_already_holds() -> None:
    taken = {"worktree-development", "worktree-development-2"}
    assert planning.unique_slug("Worktree development", taken) == "worktree-development-3"


def test_a_very_long_title_is_cut_to_a_usable_file_name() -> None:
    slug = planning.unique_slug("word " * 100, set())
    assert 0 < len(slug) <= 80
    assert not slug.endswith("-")


@pytest.mark.parametrize(
    ("candidates", "expected"),
    [
        ((TYPE_USER,), TYPE_USER),
        (("", TYPE_FEEDBACK), TYPE_FEEDBACK),
        (("invented", "also-invented"), TYPE_PROJECT),
        ((), TYPE_PROJECT),
    ],
)
def test_a_stray_type_never_travels_into_a_note(candidates: tuple[str, ...], expected: str) -> None:
    assert planning.note_type(*candidates) == expected


# --- the four actions --------------------------------------------------------


@pytest.mark.asyncio
async def test_an_open_starts_a_new_note_named_from_the_proposed_title() -> None:
    entry = _entry("one")
    plan, _ = await _plan(
        [entry],
        [
            _actions(
                {
                    "entry": entry.entry_id,
                    "action": "open",
                    "title": "Worktree trap",
                    "type": "project",
                }
            )
        ],
    )

    assert list(plan.targets) == ["worktree-trap"]
    target = plan.targets["worktree-trap"]
    assert target.existing is None
    assert target.entries == [entry]
    assert target.type == TYPE_PROJECT


@pytest.mark.asyncio
async def test_a_merge_routes_the_entry_into_the_note_it_names() -> None:
    entry = _entry("one")
    existing = _note("worktree-trap")

    plan, _ = await _plan(
        [entry],
        [_actions({"entry": entry.entry_id, "action": "merge", "slug": "worktree-trap"})],
        notes=[existing],
    )

    assert plan.targets["worktree-trap"].existing == existing
    assert plan.targets["worktree-trap"].entries == [entry]


@pytest.mark.asyncio
async def test_two_agents_entries_can_share_one_note_by_naming_each_other() -> None:
    """On a fresh partition there is no index at all, so the cross-agent merge
    this layer exists for can only happen sibling-to-sibling (see "Record
    provenance and merge by meaning")."""
    first = _entry("one", agent="claude-code")
    second = _entry("two", agent="codex")
    ordered = sorted([first, second], key=lambda e: e.entry_id)

    plan, _ = await _plan(
        [first, second],
        [
            _actions(
                {"entry": ordered[0].entry_id, "action": "open", "title": "The venv trap"},
                {"entry": ordered[1].entry_id, "action": "merge", "slug": ordered[0].entry_id},
            )
        ],
    )

    assert len(plan.targets) == 1
    (target,) = plan.targets.values()
    assert {e.agent for e in target.entries} == {"claude-code", "codex"}


@pytest.mark.asyncio
async def test_a_merge_into_a_sibling_that_was_dropped_degrades_to_nothing() -> None:
    first, second = _entry("one"), _entry("two")
    plan, _ = await _plan(
        [first, second],
        [
            _actions(
                {"entry": first.entry_id, "action": "drop", "reason": "transient"},
                {"entry": second.entry_id, "action": "merge", "slug": first.entry_id},
            )
        ],
    )

    assert plan.targets == {}
    assert [e.entry_id for e, _ in plan.drops] == [first.entry_id]


@pytest.mark.asyncio
async def test_a_retirement_names_the_entry_that_contradicted_it_as_its_replacement() -> None:
    entry = _entry("one")
    plan, _ = await _plan(
        [entry],
        [
            _actions(
                {
                    "entry": entry.entry_id,
                    "action": "retire",
                    "slug": "old-note",
                    "reason": "the mechanism was removed",
                }
            )
        ],
        notes=[_note("old-note")],
    )

    record = plan.retirements["old-note"]
    assert record.reason == "the mechanism was removed"
    assert record.replaced_by in plan.targets
    assert plan.targets[record.replaced_by].entries == [entry]
    # The doomed note's own entries go on the record with it, so they are not
    # re-judged on the next pass.
    assert record.entry_ids == (_note("old-note").origins[0].key,)


@pytest.mark.asyncio
async def test_a_drop_is_an_ordinary_outcome_that_writes_no_note() -> None:
    entry = _entry("one")
    plan, _ = await _plan(
        [entry],
        [_actions({"entry": entry.entry_id, "action": "drop", "reason": "says nothing durable"})],
    )

    assert plan.targets == {}
    assert plan.retirements == {}
    assert plan.drops == [(entry, "says nothing durable")]


# --- the rules a prompt cannot hold ------------------------------------------


@pytest.mark.asyncio
async def test_a_note_being_written_this_pass_is_not_also_retired() -> None:
    first, second = _entry("one"), _entry("two")
    ordered = sorted([first, second], key=lambda e: e.entry_id)

    plan, _ = await _plan(
        [first, second],
        [
            _actions({"entry": ordered[0].entry_id, "action": "merge", "slug": "old-note"}),
            _actions(
                {
                    "entry": ordered[1].entry_id,
                    "action": "retire",
                    "slug": "old-note",
                    "reason": "contradicted",
                }
            ),
        ],
        notes=[_note("old-note")],
        chunk_size=1,
    )

    assert "old-note" in plan.targets
    assert plan.retirements == {}


@pytest.mark.asyncio
async def test_a_note_being_retired_this_pass_is_not_also_merged_into() -> None:
    first, second = _entry("one"), _entry("two")
    ordered = sorted([first, second], key=lambda e: e.entry_id)

    plan, _ = await _plan(
        [first, second],
        [
            _actions(
                {
                    "entry": ordered[0].entry_id,
                    "action": "retire",
                    "slug": "old-note",
                    "reason": "contradicted",
                }
            ),
            _actions({"entry": ordered[1].entry_id, "action": "merge", "slug": "old-note"}),
        ],
        notes=[_note("old-note")],
        chunk_size=1,
    )

    assert "old-note" in plan.retirements
    assert "old-note" not in plan.targets


@pytest.mark.asyncio
async def test_a_later_chunk_may_merge_into_a_note_an_earlier_one_opened() -> None:
    first, second = _entry("one"), _entry("two")
    ordered = sorted([first, second], key=lambda e: e.entry_id)

    plan, completion = await _plan(
        [first, second],
        [
            _actions({"entry": ordered[0].entry_id, "action": "open", "title": "Shared subject"}),
            _actions({"entry": ordered[1].entry_id, "action": "merge", "slug": "shared-subject"}),
        ],
        chunk_size=1,
    )

    assert len(completion.calls) == 2
    assert list(plan.targets) == ["shared-subject"]
    assert len(plan.targets["shared-subject"].entries) == 2


@pytest.mark.asyncio
async def test_every_retirement_this_pass_decided_is_shown_to_the_next_chunk() -> None:
    """Including the ones decided a moment ago, or the second chunk re-opens
    what the first removed (see "Record retirements so they stick")."""
    first, second = _entry("one"), _entry("two")
    ordered = sorted([first, second], key=lambda e: e.entry_id)

    _, completion = await _plan(
        [first, second],
        [
            _actions(
                {
                    "entry": ordered[0].entry_id,
                    "action": "retire",
                    "slug": "old-note",
                    "reason": "contradicted",
                }
            ),
            _actions({"entry": ordered[1].entry_id, "action": "drop", "reason": "same subject"}),
        ],
        notes=[_note("old-note")],
        retired=[RetiredNote(slug="older", title="An older subject", reason="r")],
        chunk_size=1,
    )

    second_request = json.loads(str(completion.calls[1]["user"]))
    assert "An older subject" in second_request["retired_subjects"]
    assert "Old Note" in second_request["retired_subjects"]


@pytest.mark.asyncio
async def test_a_chunk_the_model_could_not_answer_leaves_its_entries_undistilled() -> None:
    entry = _entry("one")
    plan, _ = await _plan([entry], ["not json at all"])

    assert plan.targets == {}
    assert plan.retirements == {}
    assert plan.drops == []


async def test_the_operators_bound_reaches_the_request(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A bound that stops at the pass boundary is a setting that does nothing.

    This is the failure the whole seam exists to rule out, and it is invisible
    from the outside: routing that times out defers its entries silently, so a
    bound the operator raised but that never reached the request looks exactly
    like a bound that did.
    """
    completion = ScriptedCompletion(['{"actions": []}'])
    await planning.build_plan(
        _PARTITION,
        [_entry("a")],
        notes=[],
        retired=[],
        model="a-model",
        completion=completion,  # type: ignore[arg-type]
        credential_resolver=lambda ref: ref,
        timeout=222.0,
        chunk_size=20,
    )

    assert completion.calls[0]["timeout"] == 222.0
