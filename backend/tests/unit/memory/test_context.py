"""The session-start payload: the whole index, and where the bodies are.

Delivery is no longer a digest (FR-028). Every non-retired note in the current
repository's partition and in ``global`` gets one line, and beneath them sits
the **absolute path** of the directory those notes live in — named as a
directory to read files out of, with no tool named for it.

Two measured failures are pinned here as tests, because they are the reasons
this module was rewritten:

* The previous design spent a ~600-token budget on ``global`` first and
  therefore delivered, on a live vault of 189 entries, 8 lines of which
  **none** were about the project the session was open in. Under a ceiling the
  current repository now wins (FR-030).
* It named a tool as the way to reach a body, and in three weeks no agent ever
  called it. The payload now names a path.

``MemoryPort`` is faked: composing needs scope and reads, never a database.
The port's own promise — ``list_notes`` answers from ``notes/``, so a retired
note is not there to filter — is exercised for real in
``tests/integration/memory/test_distil_lifecycle.py``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from coffer.application.memory.context import (
    DEFAULT_CEILING_TOKENS,
    compose_context,
)
from coffer.application.memory.index import recency
from coffer.domain.memory.note import TYPE_PROJECT, TYPE_USER, Note, Origin
from coffer.infrastructure.memory import paths as memory_paths

_REPOSITORY = "/home/dev/coffer"


@dataclass(frozen=True)
class _Partition:
    name: str
    repository_path: str


class _FakeMemory:
    """The narrow slice ``compose_context`` composes against."""

    def __init__(
        self,
        notes: dict[str, list[Note]],
        *,
        partitions: Sequence[_Partition],
        visible: Sequence[str] | None = None,
    ) -> None:
        self._notes = notes
        self._partitions = list(partitions)
        self._visible = list(visible) if visible is not None else [p.name for p in partitions]

    async def visible_partitions(self, agent: str | None) -> list[str]:
        return list(self._visible)

    async def list_notes(self, partition: str, *, agent: str | None = None) -> list[Note]:
        if agent is not None and partition not in self._visible:
            return []
        return list(self._notes.get(partition, []))

    async def list_partitions(self) -> list[_Partition]:
        return list(self._partitions)


def _note(
    slug: str,
    partition: str,
    *,
    description: str = "the conclusion, on one line",
    type: str = TYPE_PROJECT,
    updated_at: str = "2026-01-01",
    search_terms: tuple[str, ...] = (),
) -> Note:
    return Note(
        slug=slug,
        title=slug.replace("-", " "),
        description=description,
        type=type,
        body="a body that is never delivered",
        partition=partition,
        origins=(Origin(agent="codex", native_path=f"/native/{partition}/{slug}.md", anchor=slug),),
        created_at="2026-01-01",
        updated_at=updated_at,
        search_terms=search_terms,
    )


def _memory(*, project_notes: int = 2, global_notes: int = 2) -> _FakeMemory:
    return _FakeMemory(
        {
            "coffer": [_note(f"project-{i}", "coffer") for i in range(project_notes)],
            "global": [
                _note(f"personal-{i}", "global", type=TYPE_USER) for i in range(global_notes)
            ],
        },
        partitions=[_Partition("coffer", _REPOSITORY), _Partition("global", "")],
    )


# --- the whole index, and the path ------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory",
    scenario="the composed context carries the whole index and the path to the bodies",
)
async def test_every_note_in_both_partitions_gets_exactly_one_line() -> None:
    from coffer.application.memory.index import index_line

    memory = _memory(project_notes=3, global_notes=2)

    composed = await compose_context(memory, agent="codex", cwd=f"{_REPOSITORY}/backend")

    assert composed.partition == "coffer"
    assert composed.notes_included == 5
    assert composed.notes_omitted == 0
    lines = composed.text.split("\n")
    for partition in ("coffer", "global"):
        for note in await memory.list_notes(partition):
            assert lines.count(index_line(note)) == 1


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory",
    scenario="the composed context carries the whole index and the path to the bodies",
)
async def test_the_payload_names_the_absolute_notes_path_and_no_tool() -> None:
    composed = await compose_context(_memory(), agent="codex", cwd=_REPOSITORY)

    notes_dir = str(memory_paths.notes_dir("coffer"))
    assert notes_dir in composed.text
    assert notes_dir.startswith("/")
    assert "read one as a file" in composed.text
    # FR-028: every consumer reads files already, so no tool is named for it.
    for tool in ("coffer__recall", "coffer__read", "coffer__search", "MCP", "tool"):
        assert tool not in composed.text


@pytest.mark.asyncio
async def test_the_repository_is_named_so_the_session_knows_which_project() -> None:
    composed = await compose_context(_memory(), agent="codex", cwd=_REPOSITORY)
    assert "partition `coffer`" in composed.text
    assert _REPOSITORY in composed.text


@pytest.mark.asyncio
async def test_a_directory_in_no_partition_still_gets_what_is_known_about_the_developer() -> None:
    composed = await compose_context(_memory(), agent="codex", cwd="/tmp/scratch-2026-09-17")

    assert composed.partition == "global"
    assert "personal-0" in composed.text
    assert "in no repository Coffer has aggregated yet" in composed.text


@pytest.mark.asyncio
async def test_a_nested_repository_resolves_to_the_inner_one() -> None:
    memory = _FakeMemory(
        {"outer": [_note("o", "outer")], "inner": [_note("i", "inner")], "global": []},
        partitions=[
            _Partition("outer", "/home/dev/outer"),
            _Partition("inner", "/home/dev/outer/vendor/inner"),
            _Partition("global", ""),
        ],
    )
    composed = await compose_context(memory, agent=None, cwd="/home/dev/outer/vendor/inner/src")
    assert composed.partition == "inner"


@pytest.mark.asyncio
async def test_nothing_to_deliver_is_an_empty_payload_not_a_bare_header() -> None:
    """FR-031's channel turn appends this only when it is non-empty."""
    memory = _FakeMemory({}, partitions=[_Partition("global", "")])
    composed = await compose_context(memory, agent="codex", cwd=_REPOSITORY)
    assert composed.text == ""
    assert composed.notes_included == 0


@pytest.mark.asyncio
async def test_a_partition_out_of_the_agents_scope_contributes_nothing() -> None:
    memory = _FakeMemory(
        {"coffer": [_note("p", "coffer")], "global": [_note("g", "global", type=TYPE_USER)]},
        partitions=[_Partition("coffer", _REPOSITORY), _Partition("global", "")],
        visible=["global"],
    )
    composed = await compose_context(memory, agent="codex", cwd=_REPOSITORY)
    assert "`p.md`" not in composed.text
    assert "`g.md`" in composed.text


# --- the ceiling -------------------------------------------------------------


async def _binding_ceiling(memory: _FakeMemory, *, room_for: int) -> int:
    """A ceiling that fits the scaffolding and ``room_for`` lines, no more.

    Measured rather than hard-coded, because the scaffolding's own size moves
    with the absolute notes path — which is a ``tmp_path`` here and a short
    ``~/.coffer/...`` in production. A literal would pin this test to one
    machine's path length.
    """
    from coffer.domain.memory.budget import estimate_tokens

    full = await compose_context(memory, agent="codex", cwd=_REPOSITORY)
    assert full.notes_omitted == 0, "the untrimmed payload is the baseline"
    lines = [line for line in full.text.split("\n") if line.startswith("- **")]
    scaffolding = estimate_tokens(full.text) - sum(estimate_tokens(line) for line in lines)
    # Both trim notices are reserved up front, so a trim can never crowd out
    # the line that announces it — the baseline above carries neither.
    for partition in ("global", "coffer"):
        scaffolding += estimate_tokens(
            f"(99 older line(s) not shown — those notes are files in "
            f"{memory_paths.notes_dir(partition)})"
        )
    widest = max(estimate_tokens(line) for line in lines)
    return scaffolding + widest * room_for


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="an index too large for the ceiling is trimmed and says so"
)
async def test_the_current_repositorys_lines_survive_and_globals_are_dropped() -> None:
    """The reverse of what this layer did before, and the direct cause of the
    measured 8-of-189 failure (FR-030)."""
    memory = _memory(project_notes=6, global_notes=6)
    ceiling = await _binding_ceiling(memory, room_for=8)

    composed = await compose_context(memory, agent="codex", cwd=_REPOSITORY, ceiling_tokens=ceiling)

    assert composed.notes_omitted > 0
    for i in range(6):
        assert f"`project-{i}.md`" in composed.text
    assert any(f"`personal-{i}.md`" not in composed.text for i in range(6))
    assert "older line(s) not shown" in composed.text


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="an index too large for the ceiling is trimmed and says so"
)
async def test_a_trim_names_how_many_were_dropped_and_the_directory_holding_them() -> None:
    memory = _memory(project_notes=40, global_notes=0)
    ceiling = await _binding_ceiling(memory, room_for=10)

    composed = await compose_context(memory, agent="codex", cwd=_REPOSITORY, ceiling_tokens=ceiling)

    assert composed.notes_omitted > 0
    notice = f"({composed.notes_omitted} older line(s) not shown"
    assert notice in composed.text
    assert str(memory_paths.notes_dir("coffer")) in composed.text


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="an index too large for the ceiling is trimmed and says so"
)
async def test_the_trim_drops_the_oldest_lines_rather_than_an_arbitrary_set() -> None:
    memory = _FakeMemory(
        {
            "coffer": [
                _note(f"note-{year}", "coffer", updated_at=f"20{year}-01-01")
                for year in (20, 21, 22, 23, 24, 25, 26)
            ],
            "global": [],
        },
        partitions=[_Partition("coffer", _REPOSITORY), _Partition("global", "")],
    )
    ceiling = await _binding_ceiling(memory, room_for=4)

    composed = await compose_context(memory, agent="codex", cwd=_REPOSITORY, ceiling_tokens=ceiling)

    assert composed.notes_included >= 1
    kept = [y for y in (20, 21, 22, 23, 24, 25, 26) if f"`note-{y}.md`" in composed.text]
    # A contiguous newest-first prefix: whatever survived, nothing older than
    # the oldest survivor did.
    assert kept == sorted(kept)
    assert 26 in kept
    assert composed.notes_omitted == 7 - len(kept)


@pytest.mark.asyncio
async def test_notes_written_in_one_pass_still_sort_by_when_they_were_written() -> None:
    """The trim's order must not collapse when everything shares a timestamp.

    ``recency`` used to take the ``max()`` of a note's ``updated_at``, its
    ``created_at`` and every origin's capture time. Right after a rebuild all
    three are the same instant for every note — which is exactly the state an
    installation is in the first time delivery runs — so every key tied, the
    newest-first sort degenerated into whatever order the notes arrived in,
    and the trim took them off the *tail*: the newest note, dropped first.
    """
    notes = [
        _note(f"note-{year}", "coffer", updated_at=f"20{year}-01-01")
        for year in (20, 21, 22, 23, 24, 25, 26)
    ]
    # What a rebuild produces: one shared creation instant, later than every
    # note's own last-written date, on every note.
    notes = [dataclasses.replace(n, created_at="2026-06-01") for n in notes]

    ordered = [n.slug for n in sorted(notes, key=recency, reverse=True)]

    assert ordered[0] == "note-26"
    assert ordered[-1] == "note-20"


@pytest.mark.asyncio
async def test_the_payload_stays_at_or_under_the_ceiling() -> None:
    from coffer.domain.memory.budget import estimate_tokens

    memory = _memory(project_notes=50, global_notes=50)
    ceiling = await _binding_ceiling(memory, room_for=12)
    composed = await compose_context(memory, agent="codex", cwd=_REPOSITORY, ceiling_tokens=ceiling)
    assert composed.notes_omitted > 0
    assert estimate_tokens(composed.text) <= ceiling


@pytest.mark.asyncio
async def test_an_ordinary_index_is_nowhere_near_the_default_ceiling() -> None:
    """The ceiling guards the assumption breaking; it is not the ordinary path
    the previous ~600-token budget made it."""
    memory = _memory(project_notes=40, global_notes=20)
    composed = await compose_context(memory, agent="codex", cwd=_REPOSITORY)
    assert composed.notes_omitted == 0
    assert DEFAULT_CEILING_TOKENS >= 9000
