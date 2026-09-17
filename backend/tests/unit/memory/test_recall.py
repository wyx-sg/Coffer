"""``coffer__recall`` — a locator, not a reader (FR-035, FR-034).

Three properties, and the third is a bug being kept fixed rather than a
feature being restated:

* an answer is a **path**, a title and a description — never a body, because
  the caller is a local process that reads files;
* it spans only the partitions the calling agent's scope allows;
* **a retired note never comes back.** The previous version filtered nothing,
  so 11 facts that had been marked superseded — and were correctly withheld
  from delivery — were still answerable here as if current. The mechanism now
  is structural: a retirement takes the file out of ``notes/``, and this reads
  only what ``list_notes`` returns.

That last one is asserted twice: here against a fake port (the contract), and
in ``tests/integration/memory/test_distil_lifecycle.py`` against the real
service and a real retirement (the mechanism).
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from coffer.application.memory.recall import RecallService
from coffer.domain.memory.note import TYPE_PROJECT, TYPE_USER, Note, Origin
from coffer.infrastructure.memory import paths as memory_paths


class _FakeMemory:
    def __init__(self, notes: dict[str, list[Note]], *, visible: Sequence[str] | None = None):
        self._notes = notes
        self._visible = list(visible) if visible is not None else sorted(notes)

    async def visible_partitions(self, agent: str | None) -> list[str]:
        return list(self._visible)

    async def list_notes(self, partition: str, *, agent: str | None = None) -> list[Note]:
        if agent is not None and partition not in self._visible:
            return []
        return list(self._notes.get(partition, []))


def _note(
    slug: str,
    partition: str,
    *,
    body: str = "a body",
    title: str = "",
    description: str = "a description",
    type: str = TYPE_PROJECT,
    search_terms: tuple[str, ...] = (),
) -> Note:
    return Note(
        slug=slug,
        title=title or slug,
        description=description,
        type=type,
        body=body,
        partition=partition,
        origins=(Origin(agent="codex", native_path=f"/n/{slug}.md", anchor=slug),),
        search_terms=search_terms,
    )


def _service(notes: dict[str, list[Note]], **kw: object) -> RecallService:
    return RecallService(memory=_FakeMemory(notes, **kw))  # type: ignore[arg-type]


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="recall answers with locations, and never with a retired note"
)
async def test_a_match_comes_back_as_an_absolute_path_a_title_and_a_description() -> None:
    service = _service(
        {"coffer": [_note("venv", "coffer", body="worktrees have no .venv", title="The venv trap")]}
    )

    outcome = await service.recall("no .venv")

    assert len(outcome.notes) == 1
    found = outcome.notes[0]
    assert found.path == str(memory_paths.note_path("coffer", "venv"))
    assert found.path.startswith("/")
    assert (found.title, found.description, found.partition) == (
        "The venv trap",
        "a description",
        "coffer",
    )


@pytest.mark.asyncio
async def test_every_answer_points_inside_the_partitions_notes_directory() -> None:
    """Which is how ``.raw/`` and a retired note stay out (FR-008, FR-025):
    recall reads ``list_notes`` and nothing else, so there is no other
    directory for an answer to come from. The retirement half of that is
    exercised against a real pass in
    ``tests/integration/memory/test_distil_lifecycle.py``."""
    service = _service(
        {
            "coffer": [_note("current", "coffer", body="a shared phrase")],
            "global": [_note("personal", "global", body="a shared phrase", type=TYPE_USER)],
        }
    )

    outcome = await service.recall("a shared phrase")

    assert {n.path for n in outcome.notes} == {
        str(memory_paths.note_path("coffer", "current")),
        str(memory_paths.note_path("global", "personal")),
    }
    assert all(n.path.endswith(".md") for n in outcome.notes)


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="recall answers with locations, and never with a retired note"
)
async def test_an_answer_carries_no_score_no_mode_and_no_reason() -> None:
    service = _service({"coffer": [_note("a", "coffer", body="matching phrase")]})
    outcome = await service.recall("matching phrase")
    fields = set(vars(outcome.notes[0]))
    assert fields == {"path", "title", "description", "type", "partition"}


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="recall answers with locations, and never with a retired note"
)
async def test_recall_spans_only_the_partitions_the_calling_agent_may_see() -> None:
    service = _service(
        {
            "coffer": [_note("visible", "coffer", body="a shared phrase")],
            "other": [_note("hidden", "other", body="a shared phrase")],
        },
        visible=["coffer"],
    )

    outcome = await service.recall("a shared phrase", agent="codex")

    assert [n.partition for n in outcome.notes] == ["coffer"]


@pytest.mark.asyncio
async def test_a_match_never_returns_the_body_itself() -> None:
    body = "the whole body, which a caller reads for itself"
    service = _service({"coffer": [_note("a", "coffer", body=body)]})
    outcome = await service.recall("whole body")
    assert body not in str(outcome.notes[0])


@pytest.mark.asyncio
async def test_matching_is_case_insensitive_and_literal() -> None:
    service = _service({"coffer": [_note("a", "coffer", body="Always Use A Worktree")]})
    assert len((await service.recall("always use a worktree")).notes) == 1
    assert len((await service.recall("worktrees are")).notes) == 0


@pytest.mark.asyncio
async def test_a_note_matches_on_the_search_terms_its_source_supplied() -> None:
    """Codex's own answer to "what would you look this up up by" (FR-004) —
    ignoring it here would waste the one hint the corpus carries."""
    service = _service(
        {"coffer": [_note("a", "coffer", body="nothing relevant", search_terms=("port drift",))]}
    )
    outcome = await service.recall("PORT DRIFT")
    assert len(outcome.notes) == 1


@pytest.mark.asyncio
async def test_a_note_matches_on_its_title_or_description() -> None:
    service = _service(
        {
            "coffer": [
                _note("a", "coffer", title="Daemon restart", body="x"),
                _note("b", "coffer", description="the ceiling binds here", body="y"),
            ]
        }
    )
    assert len((await _service({}).recall("anything")).notes) == 0
    assert [n.title for n in (await service.recall("daemon restart")).notes] == ["Daemon restart"]
    assert [n.path for n in (await service.recall("ceiling binds")).notes] == [
        str(memory_paths.note_path("coffer", "b"))
    ]


@pytest.mark.asyncio
async def test_an_empty_query_answers_nothing_rather_than_everything() -> None:
    service = _service({"coffer": [_note("a", "coffer")]})
    assert (await service.recall("   ")).notes == ()


@pytest.mark.asyncio
async def test_a_vault_with_no_notes_answers_nothing() -> None:
    assert (await _service({"coffer": []}).recall("anything")).notes == ()


@pytest.mark.asyncio
async def test_results_are_ordered_by_path_so_one_query_answers_the_same_way_twice() -> None:
    service = _service(
        {
            "coffer": [_note(s, "coffer", body="shared") for s in ("zebra", "alpha", "middle")],
            "global": [_note("also", "global", body="shared", type=TYPE_USER)],
        }
    )
    first = await service.recall("shared")
    second = await service.recall("shared")
    assert [n.path for n in first.notes] == [n.path for n in second.notes]
    assert [n.path for n in first.notes] == sorted(n.path for n in first.notes)


@pytest.mark.asyncio
async def test_top_k_bounds_the_answer() -> None:
    service = _service({"coffer": [_note(f"n{i}", "coffer", body="shared") for i in range(12)]})
    assert len((await service.recall("shared", top_k=3)).notes) == 3
    assert len((await service.recall("shared")).notes) == 10
