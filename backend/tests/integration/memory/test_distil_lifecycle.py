"""A partition's whole life: aggregate, distil, merge, retire — and stay retired.

Real store, real repository, real service; the internal connection is a
scripted completion, because a model is the one dependency this tier does not
run. What is exercised is the sequence, which is where the layer's value and
its risk both sit:

* two agents' differently-worded entries becoming **one** note ("Record
  provenance and merge by meaning") — matched on meaning, because on the
  maintainer's live vault 378 entries from two agents produced **zero**
  cross-agent matches under literal comparison;
* a later entry **rewriting** the note it belongs to rather than adding a
  second beside it ("Keep one topic per note");
* a retirement that **sticks**: the note leaves ``notes/``, the record goes
  into ``RETIRED.md``, and the next pass over unchanged sources does not
  re-open it ("Record retirements so they stick") — nor does it reach delivery
  or recall, which is the specific bug the previous design had, where 11 dead
  facts stayed answerable.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from coffer.application.memory.context import compose_context
from coffer.application.memory.recall import RecallService
from coffer.application.memory.service import KIND_MEMORY
from coffer.domain.memory.note import TYPE_PROJECT
from coffer.infrastructure.memory import paths, store
from coffer.infrastructure.memory.raw_store import list_raw_entries
from tests.integration.memory.conftest import FakeResources, init_repository
from tests.unit.memory.conftest import (
    FakeReader,
    ScriptedCompletion,
    StubModelSelector,
    memory_service,
    raw_entry,
)

_PARTITION = "coffer"


def _route(*items: dict[str, Any]) -> str:
    return json.dumps({"actions": list(items)})


def _write(title: str, description: str, body: str) -> str:
    return json.dumps({"title": title, "description": description, "body": body})


class _Vault:
    """One repository, two agents, and a completion a test scripts per pass."""

    def __init__(self, tmp_path: pathlib.Path) -> None:
        self.repository = init_repository(
            tmp_path / "home" / "dev" / "coffer", remote="git@github.com:owner/coffer.git"
        )
        self.resources = FakeResources()
        self.resources.add_agent("claude-code", "claude_code", "/cc")
        self.resources.add_agent("codex", "codex", "/cx")
        self.claude = FakeReader(agent_type="claude_code")
        self.codex = FakeReader(agent_type="codex")
        self.completion = ScriptedCompletion([])

    def service(self):  # type: ignore[no-untyped-def]
        return memory_service(
            self.resources,
            {"claude_code": self.claude, "codex": self.codex},
            completion=self.completion,
            model_selector=StubModelSelector(),
        )

    def claude_says(self, title: str, body: str, *, digest: str, anchor: str = "") -> None:
        path = "/cc/projects/coffer/memory/f.md"
        self.claude.set_source(
            "/cc",
            path,
            digest,
            (raw_entry(title, body, anchor=anchor or title, project_root=str(self.repository)),),
        )
        self.claude.set_digest("/cc", path, digest)
        self.claude.content[path] = (
            raw_entry(title, body, anchor=anchor or title, project_root=str(self.repository)),
        )

    def codex_says(self, title: str, body: str, *, digest: str, anchor: str = "") -> None:
        path = "/cx/memories/MEMORY.md"
        self.codex.set_source(
            "/cx",
            path,
            digest,
            (raw_entry(title, body, anchor=anchor or title, project_root=str(self.repository)),),
        )
        self.codex.set_digest("/cx", path, digest)
        self.codex.content[path] = (
            raw_entry(title, body, anchor=anchor or title, project_root=str(self.repository)),
        )

    async def pass_over(self, answers: list[str]):  # type: ignore[no-untyped-def]
        self.completion._responses.extend(answers)
        service = self.service()
        await service.aggregate()
        # Aggregation is what registers the partition, so its uid only exists
        # after that half has run — which is also the order production takes:
        # nothing can be distilled before something has filed into it.
        return await service.distil(self.resources.uid_of(KIND_MEMORY, _PARTITION))


@pytest.fixture
def vault(tmp_path: pathlib.Path) -> _Vault:
    return _Vault(tmp_path)


def _entry_ids() -> list[str]:
    return sorted(e.entry_id for e in list_raw_entries(_PARTITION))


# --- two agents, one note ----------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="two agents' differently-worded entries distil into one note"
)
async def test_two_agents_accounts_of_one_lesson_become_one_note_naming_both(
    vault: _Vault,
) -> None:
    vault.claude_says("Worktree has no .venv", "This repo's worktrees have no .venv.", digest="a1")
    vault.codex_says(
        "Linked checkout build failure", "Builds fail in a linked checkout.", digest="b1"
    )

    service = vault.service()
    await service.aggregate()
    first, second = _entry_ids()
    result = await vault.pass_over(
        [
            _route(
                {"entry": first, "action": "open", "title": "The venv trap", "type": "project"},
                {"entry": second, "action": "merge", "slug": first},
            ),
            _write(
                "The venv trap",
                "worktrees have no .venv — symlink the main one first",
                "Both agents hit this: a worktree has no `.venv`.",
            ),
        ]
    )

    notes = store.list_notes(_PARTITION)
    assert len(notes) == 1
    note = notes[0]
    assert note.agents == ("claude-code", "codex") or note.agents == ("codex", "claude-code")
    assert len(note.origins) == 2
    assert result.opened == 1
    # The note is Coffer's own writing, not either source's ("Write notes in
    # Coffer's own words").
    assert note.body.startswith("Both agents hit this")


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="two agents' differently-worded entries distil into one note"
)
async def test_neither_raw_entry_is_modified_or_deleted_by_the_pass(vault: _Vault) -> None:
    vault.claude_says("A", "Claude Code's own words.", digest="a1")
    vault.codex_says("B", "Codex's own words.", digest="b1")
    service = vault.service()
    await service.aggregate()
    before = {
        str(p): (p.read_bytes(), p.stat().st_mtime)
        for p in sorted(paths.raw_dir(_PARTITION).iterdir())
    }
    first, second = _entry_ids()

    await vault.pass_over(
        [
            _route(
                {"entry": first, "action": "open", "title": "Shared"},
                {"entry": second, "action": "merge", "slug": first},
            ),
            _write("Shared", "one line", "Coffer's prose."),
        ]
    )

    after = {
        str(p): (p.read_bytes(), p.stat().st_mtime)
        for p in sorted(paths.raw_dir(_PARTITION).iterdir())
    }
    assert after == before
    assert len(list_raw_entries(_PARTITION)) == 2


# --- a note accumulates ------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory",
    scenario="a new raw entry updates the note it belongs to rather than adding one",
)
async def test_a_later_entry_rewrites_the_note_it_belongs_to(vault: _Vault) -> None:
    vault.codex_says("Daemon restart", "Restart with coffer daemon stop/start.", digest="b1")
    service = vault.service()
    await service.aggregate()
    (first,) = _entry_ids()
    await vault.pass_over(
        [
            _route({"entry": first, "action": "open", "title": "Daemon restart"}),
            _write("Daemon restart", "restart with stop/start", "Restart the daemon."),
        ]
    )
    note_before = store.read_note(_PARTITION, "daemon-restart")

    vault.claude_says("Port drift", "The port drifts after a restart.", digest="a2")
    service = vault.service()
    await service.aggregate()
    added = next(e for e in _entry_ids() if e != first)
    result = await vault.pass_over(
        [
            _route({"entry": added, "action": "merge", "slug": "daemon-restart"}),
            _write(
                "Daemon restart",
                "restart with stop/start — the port drifts afterwards",
                "Restart the daemon. The port drifts, so re-check it.",
            ),
        ]
    )

    notes = store.list_notes(_PARTITION)
    assert len(notes) == 1  # rewritten, not doubled
    note = notes[0]
    assert "port drifts" in note.body
    assert len(note.origins) == 2
    assert note.created_at == note_before.created_at
    assert note.updated_at > note_before.updated_at
    assert (result.merged, result.opened) == (1, 0)


# --- a retirement sticks -----------------------------------------------------


async def _retire_one(vault: _Vault) -> None:
    """Open a note, then let a later entry contradict it."""
    vault.codex_says("The mechanism shipped", "Session injection shipped in July.", digest="b1")
    service = vault.service()
    await service.aggregate()
    (first,) = _entry_ids()
    await vault.pass_over(
        [
            _route({"entry": first, "action": "open", "title": "Session injection"}),
            _write("Session injection", "session injection shipped", "It shipped in July."),
        ]
    )

    vault.claude_says("It was removed", "Session injection was removed in September.", digest="a2")
    service = vault.service()
    await service.aggregate()
    contradicting = next(e for e in _entry_ids() if e != first)
    await vault.pass_over(
        [
            _route(
                {
                    "entry": contradicting,
                    "action": "retire",
                    "slug": "session-injection",
                    "title": "Session injection removed",
                    "reason": "Removed in September.\n\n---\n\nSee the September rewrite.",
                }
            ),
            _write(
                "Session injection removed",
                "session injection was removed in September",
                "It was removed; nothing injects now.",
            ),
        ]
    )


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="a retired note leaves the index and stays out")
async def test_a_retired_notes_file_leaves_notes_and_its_record_names_what_replaced_it(
    vault: _Vault,
) -> None:
    await _retire_one(vault)

    assert not paths.note_path(_PARTITION, "session-injection").exists()
    slugs = [n.slug for n in store.list_notes(_PARTITION)]
    assert "session-injection" not in slugs
    assert slugs == ["session-injection-removed"]

    (record,) = store.read_retired(_PARTITION)
    assert record.slug == "session-injection"
    assert record.replaced_by == "session-injection-removed"
    # A reason may be prose, horizontal rule and all — and it must round-trip,
    # or the exclusion list comes back empty and every retirement is undone.
    assert record.reason.startswith("Removed in September.")
    assert "---" in record.reason


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="a retired note leaves the index and stays out")
async def test_no_index_line_mentions_a_retired_note(vault: _Vault) -> None:
    await _retire_one(vault)

    index = store.read_index(_PARTITION)
    assert "session-injection.md" not in index
    assert "- **Session injection**" not in index
    assert "- **Session injection removed**" in index


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="a retired note leaves the index and stays out")
async def test_a_second_pass_over_unchanged_sources_does_not_re_open_it(vault: _Vault) -> None:
    """The mechanism, not a nicety: the material the note was built from still
    sits in the agent's own memory, so without ``RETIRED.md`` as input the
    next pass re-imports what the last one removed."""
    await _retire_one(vault)
    calls_before = len(vault.completion.calls)

    service = vault.service()
    result = await service.aggregate()
    assert result.sources_skipped == 2 and result.sources_read == 0
    distilled = await service.distil(vault.resources.uid_of(KIND_MEMORY, _PARTITION))

    assert len(vault.completion.calls) == calls_before  # nothing was even asked
    assert (distilled.opened, distilled.merged, distilled.retired) == (0, 0, 0)
    assert [n.slug for n in store.list_notes(_PARTITION)] == ["session-injection-removed"]
    assert not paths.note_path(_PARTITION, "session-injection").exists()
    assert [r.slug for r in store.read_retired(_PARTITION)] == ["session-injection"]


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="a retired note leaves the index and stays out")
async def test_a_retired_note_reaches_neither_delivery_nor_recall(vault: _Vault) -> None:
    """The previous design kept 11 dead facts answerable through ``recall``,
    and that is the specific bug this must never allow back."""
    await _retire_one(vault)
    service = vault.service()

    composed = await compose_context(service, cwd=str(vault.repository))
    recalled = await RecallService(memory=service).recall("session injection")

    assert composed.partition == _PARTITION
    assert "session-injection.md" not in composed.text
    assert "session-injection-removed.md" in composed.text
    assert [n.path for n in recalled.notes] == [
        str(paths.note_path(_PARTITION, "session-injection-removed"))
    ]


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="recall answers with locations, and never with a retired note"
)
async def test_recall_locates_a_live_note_by_its_absolute_path(vault: _Vault) -> None:
    await _retire_one(vault)

    recalled = await RecallService(memory=vault.service()).recall("removed in September")

    assert len(recalled.notes) == 1
    found = recalled.notes[0]
    assert found.path == str(paths.note_path(_PARTITION, "session-injection-removed"))
    assert found.partition == _PARTITION
    assert found.type == TYPE_PROJECT
    assert found.description


@pytest.mark.asyncio
async def test_an_entry_the_pass_kept_nothing_from_is_never_offered_to_a_model_twice(
    vault: _Vault,
) -> None:
    """``.raw/`` may not be pruned to express a drop ("Keep distil out of the raw
    directory"), so the record is
    what stops the same entry being routed on every pass for the rest of the
    vault's life."""
    vault.codex_says("Incidental", "A transient observation.", digest="b1")
    service = vault.service()
    await service.aggregate()
    (only,) = _entry_ids()
    await vault.pass_over(
        [_route({"entry": only, "action": "drop", "reason": "says nothing durable"})]
    )
    calls_before = len(vault.completion.calls)

    assert store.list_notes(_PARTITION) == ()
    assert [e.entry_id for e in list_raw_entries(_PARTITION)] == [only]

    service = vault.service()
    await service.aggregate()
    await service.distil(vault.resources.uid_of(KIND_MEMORY, _PARTITION))

    assert len(vault.completion.calls) == calls_before
