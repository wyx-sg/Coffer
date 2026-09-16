"""Stage one: where each new entry belongs, decided over the **index** alone.

Two properties are what the two-stage shape exists for, and both are asserted
against the request this module actually builds:

* **No note body ever reaches this stage** (FR-023). A partition of a hundred
  notes that gained three entries must cost one request over a hundred index
  lines, not a request over a hundred bodies — and this module cannot leak a
  body because it is never given one.
* **The retired subjects are input, not decoration** (FR-025). The material a
  retired note was built from still sits in the agent's own memory, so without
  that list in front of the model the next pass re-opens what the last one
  removed.

Everything a model says is then validated against the batch it was asked
about: an action naming an entry or a slug that does not exist is dropped and
logged, never applied (FR-027).
"""

from __future__ import annotations

import json

import pytest

from coffer.application.memory import distil_routing as routing
from coffer.domain.memory.note import TYPE_PROJECT, TYPE_USER
from coffer.domain.memory.reader import RawEntry
from coffer.infrastructure.memory.raw_store import StoredRawEntry


def _entry(entry_id_anchor: str, *, body: str = "a body", agent: str = "codex") -> StoredRawEntry:
    return StoredRawEntry(
        partition="coffer",
        agent=agent,
        native_path=f"/native/{agent}.md",
        captured_at="2026-01-01",
        entry=RawEntry(
            title=f"title of {entry_id_anchor}",
            description="a description",
            type=TYPE_PROJECT,
            body=body,
            anchor=entry_id_anchor,
            project_root="/home/dev/coffer",
            search_terms=("a term",),
        ),
    )


def _index(*slugs: str) -> list[routing.IndexEntry]:
    return [
        routing.IndexEntry(slug=s, title=s.title(), description=f"the conclusion for {s}")
        for s in slugs
    ]


# --- the request -------------------------------------------------------------


def test_the_request_carries_the_index_and_never_a_note_body() -> None:
    payload = json.loads(
        routing.routing_payload(
            [_entry("one")],
            index=_index("worktree-trap"),
            retired_titles=["An old subject"],
            partition="coffer",
        )
    )

    assert payload["notes"] == [
        {
            "slug": "worktree-trap",
            "title": "Worktree-Trap",
            "description": "the conclusion for worktree-trap",
        }
    ]
    assert set(payload["notes"][0]) == {"slug", "title", "description"}
    assert payload["retired_subjects"] == ["An old subject"]


def test_each_entry_names_the_agent_it_came_from() -> None:
    """The cross-agent merge is the one thing this layer exists for, and
    knowing two entries came from two agents is what makes "same subject, no
    shared words" a question worth asking (FR-018)."""
    payload = json.loads(
        routing.routing_payload(
            [_entry("one", agent="claude-code"), _entry("two", agent="codex")],
            index=[],
            retired_titles=[],
            partition="coffer",
        )
    )
    assert [e["agent"] for e in payload["entries"]] == ["claude-code", "codex"]
    assert payload["entries"][0]["search_terms"] == ["a term"]


def test_an_entrys_text_is_capped_so_one_huge_entry_cannot_blow_the_request() -> None:
    payload = json.loads(
        routing.routing_payload(
            [_entry("one", body="x" * (routing.MAX_ROUTING_TEXT_CHARS + 500))],
            index=[],
            retired_titles=[],
            partition="coffer",
        )
    )
    assert len(payload["entries"][0]["text"]) == routing.MAX_ROUTING_TEXT_CHARS


def test_the_system_prompt_forbids_re_opening_a_retired_subject() -> None:
    assert "Never open a note for a subject in the retired list" in routing.ROUTING_SYSTEM


def test_chunks_are_stable_batches_in_entry_id_order() -> None:
    entries = [_entry(a) for a in ("d", "a", "c", "b")]
    batches = routing.chunks(entries, 2)

    assert [len(b) for b in batches] == [2, 2]
    flat = [e.entry_id for b in batches for e in b]
    assert flat == sorted(flat)
    assert routing.chunks(entries, 2) == batches


def test_a_chunk_size_of_zero_still_makes_progress() -> None:
    assert [len(b) for b in routing.chunks([_entry("a"), _entry("b")], 0)] == [1, 1]


def test_no_entries_is_no_request() -> None:
    assert routing.chunks([], 5) == []


# --- reading the answer ------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ('```\n{"a": 1}\n```', '{"a": 1}'),
        ('  {"a": 1}  ', '{"a": 1}'),
    ],
)
def test_a_code_fence_a_model_added_is_stripped(raw: str, expected: str) -> None:
    assert routing.strip_code_fence(raw) == expected


@pytest.mark.parametrize("text", ["not json at all", "[1, 2, 3]", "", "null"])
def test_an_answer_that_is_not_a_json_object_contributes_nothing(text: str) -> None:
    """As safe as a model that was never asked (FR-027)."""
    assert routing.parse_json_object(text, log_key="t") == {}


def test_a_valid_answer_yields_one_action_per_entry() -> None:
    answer = json.dumps(
        {
            "actions": [
                {"entry": "e1", "action": "merge", "slug": "worktree-trap"},
                {"entry": "e2", "action": "open", "title": "New subject", "type": "user"},
                {"entry": "e3", "action": "retire", "slug": "old-note", "reason": "no longer true"},
                {"entry": "e4", "action": "drop", "reason": "transient"},
            ]
        }
    )

    actions = routing.parse_actions(
        answer, entry_ids={"e1", "e2", "e3", "e4"}, slugs={"worktree-trap", "old-note"}
    )

    assert [(a.entry_id, a.action) for a in actions] == [
        ("e1", routing.ACTION_MERGE),
        ("e2", routing.ACTION_OPEN),
        ("e3", routing.ACTION_RETIRE),
        ("e4", routing.ACTION_DROP),
    ]
    assert actions[1].title == "New subject"
    assert actions[1].type == TYPE_USER
    assert actions[2].reason == "no longer true"


def test_a_merge_may_name_a_sibling_entry_in_the_same_batch() -> None:
    """A first pass over a fresh partition has no index at all, so two agents'
    accounts of one lesson can only become one note by naming each other —
    which is precisely the cross-agent merge this layer exists for (FR-018)."""
    answer = json.dumps({"actions": [{"entry": "e2", "action": "merge", "slug": "e1"}]})

    (action,) = routing.parse_actions(answer, entry_ids={"e1", "e2"}, slugs=set())

    assert action.into_entry == "e1"
    assert action.slug == ""


def test_an_entry_may_not_merge_into_itself() -> None:
    answer = json.dumps({"actions": [{"entry": "e1", "action": "merge", "slug": "e1"}]})
    assert routing.parse_actions(answer, entry_ids={"e1"}, slugs=set()) == ()


@pytest.mark.parametrize(
    "item",
    [
        {"entry": "unknown", "action": "drop"},
        {"entry": "e1", "action": "invented"},
        {"entry": "e1", "action": "merge", "slug": "a-slug-the-model-invented"},
        {"entry": "e1", "action": "retire", "slug": "a-slug-the-model-invented"},
        {"entry": 42, "action": "drop"},
        "not even a mapping",
    ],
)
def test_an_action_naming_something_that_does_not_exist_is_dropped(item: object) -> None:
    answer = json.dumps({"actions": [item]})
    assert routing.parse_actions(answer, entry_ids={"e1"}, slugs={"real-slug"}) == ()


def test_the_first_action_for_an_entry_wins() -> None:
    """FR-023 gives an entry exactly one action, and a model that names two
    has not decided."""
    answer = json.dumps(
        {
            "actions": [
                {"entry": "e1", "action": "drop", "reason": "first"},
                {"entry": "e1", "action": "open", "title": "second"},
            ]
        }
    )

    (action,) = routing.parse_actions(answer, entry_ids={"e1"}, slugs=set())

    assert action.action == routing.ACTION_DROP
    assert action.reason == "first"


def test_an_answer_with_no_actions_array_yields_nothing() -> None:
    assert routing.parse_actions('{"result": "ok"}', entry_ids={"e1"}, slugs=set()) == ()


def test_an_invented_type_is_ignored_rather_than_carried_onto_a_note() -> None:
    answer = json.dumps(
        {"actions": [{"entry": "e1", "action": "open", "title": "T", "type": "invented"}]}
    )
    (action,) = routing.parse_actions(answer, entry_ids={"e1"}, slugs=set())
    assert action.type == ""


@pytest.mark.asyncio
async def test_a_failing_completion_routes_nothing_rather_than_raising() -> None:
    class _Broken:
        async def complete(self, **kw: object) -> str:
            raise RuntimeError("the provider is down")

    actions = await routing.route_chunk(
        [_entry("one")],
        index=[],
        retired_titles=[],
        partition="coffer",
        model="m",
        completion=_Broken(),  # type: ignore[arg-type]
        credential_resolver=lambda ref: ref,
    )

    assert actions == ()


@pytest.mark.asyncio
async def test_a_routed_chunk_validates_against_the_index_it_was_given() -> None:
    entry = _entry("one")

    class _Scripted:
        def __init__(self) -> None:
            self.user = ""

        async def complete(
            self, *, system: str, user: str, model: object, credential_resolver: object
        ) -> str:
            self.user = user
            return json.dumps(
                {"actions": [{"entry": entry.entry_id, "action": "merge", "slug": "worktree-trap"}]}
            )

    completion = _Scripted()
    actions = await routing.route_chunk(
        [entry],
        index=_index("worktree-trap"),
        retired_titles=["An old subject"],
        partition="coffer",
        model="m",
        completion=completion,  # type: ignore[arg-type]
        credential_resolver=lambda ref: ref,
    )

    assert [a.slug for a in actions] == ["worktree-trap"]
    assert "An old subject" in completion.user
