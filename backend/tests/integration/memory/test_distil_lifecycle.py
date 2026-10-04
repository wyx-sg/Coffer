"""A partition's whole life: aggregate, distil, tidy, retire — and stay retired.

Real store, real repository, real service. What is exercised is the sequence, which
is where the layer's value and its risk both sit:

* two agents' entries each becoming a note of their own (see "Distil each raw entry
  into a note mechanically"); collapsing them is the tidying agent's work;
* a merge an agent did by appending origins and deleting a file, which stays done;
* a note an agent marked retired, which leaves ``notes/``, goes into ``RETIRED.md``
  with its entry ids, and is not re-opened by the next pass over unchanged sources
  ("Record retirements so they stick") — nor does it reach delivery or a search of the
  notes.
"""

from __future__ import annotations

import pathlib
from typing import Any

import httpx
import pytest

from coffer.application.memory.context import compose_context
from coffer.application.memory.distil_worker import WORKER_ACTOR, DistilWorker
from coffer.application.memory.service import KIND_MEMORY
from coffer.domain.memory.note import TYPE_PROJECT, Note
from coffer.infrastructure.memory import note_edit, paths, store
from coffer.infrastructure.memory.raw_store import (
    StoredRawEntry,
    delete_raw_entry,
    list_raw_entries,
    write_raw_entry,
)
from tests.integration.memory.conftest import FakeResources, init_repository
from tests.unit.memory.conftest import FakeAudit, FakeReader, memory_service, raw_entry

_PARTITION = "coffer"


class _Vault:
    """One repository and two agents."""

    def __init__(self, tmp_path: pathlib.Path) -> None:
        self.repository = init_repository(
            tmp_path / "home" / "dev" / "coffer", remote="git@github.com:owner/coffer.git"
        )
        self.resources = FakeResources()
        self.resources.add_agent("claude-code", "claude_code", "/cc")
        self.resources.add_agent("codex", "codex", "/cx")
        self.claude = FakeReader(agent_type="claude_code")
        self.codex = FakeReader(agent_type="codex")

    def service(self):  # type: ignore[no-untyped-def]
        return memory_service(
            self.resources,
            {"claude_code": self.claude, "codex": self.codex},
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

    async def pass_over(self):  # type: ignore[no-untyped-def]
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


# --- two agents, two notes ---------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="a later raw entry on a covered topic opens a note of its own"
)
async def test_a_later_entry_on_a_covered_topic_opens_a_note_beside_the_first(
    vault: _Vault,
) -> None:
    vault.codex_says("Worktree has no .venv", "Worktrees have no .venv.", digest="b1")
    await vault.pass_over()
    path = paths.note_path(_PARTITION, "worktree-has-no-venv")
    first = path.read_bytes()

    vault.claude_says("Worktree venv", "A worktree needs its own .venv link.", digest="a1")
    await vault.pass_over()

    assert path.read_bytes() == first
    notes = store.list_notes(_PARTITION)
    assert len(notes) == 2
    second = next(n for n in notes if n.slug != "worktree-has-no-venv")
    assert len(second.origins) == 1


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="report what a distil pass wrote and retired")
async def test_the_audit_record_counts_the_notes_a_pass_wrote_and_retired(
    vault: _Vault,
) -> None:
    vault.codex_says("Marked", "Will be retired.", digest="b1")
    await vault.pass_over()
    marked = store.read_note(_PARTITION, "marked")
    store.write_note(type(marked)(**{**marked.__dict__, "retired": "gone for good"}))
    # A note whose only raw entry has been removed.
    gone = StoredRawEntry(
        partition=_PARTITION,
        agent="codex",
        native_path="/native/codex.md",
        captured_at="2026-01-01T00:00:00+00:00",
        entry=raw_entry("Orphan", "Orphan body.", anchor="orphan"),
    )
    write_raw_entry(gone)
    store.write_note(
        Note(
            slug="orphan",
            title="Orphan",
            description="About orphan.",
            type=TYPE_PROJECT,
            body="Orphan body.",
            partition=_PARTITION,
            origins=(gone.origin,),
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
    )
    delete_raw_entry(_PARTITION, gone.entry_id)
    vault.claude_says("Fresh", "An undistilled entry.", digest="a1")
    audit = FakeAudit()
    service = memory_service(
        vault.resources, {"claude_code": vault.claude, "codex": vault.codex}, audit=audit
    )
    await service.aggregate()

    await service.distil(vault.resources.uid_of(KIND_MEMORY, _PARTITION))

    [(_event, _actor, details)] = [e for e in audit.events if e[0] == "memory_distilled"]
    assert details == {"opened": 1, "retired": 2}
    assert audit.resources[-1] is not None and audit.resources[-1].name == _PARTITION
    assert paths.index_path(_PARTITION).is_file()


@pytest.mark.asyncio
async def test_two_agents_accounts_of_one_lesson_become_a_note_each(vault: _Vault) -> None:
    vault.claude_says("Worktree has no .venv", "This repo's worktrees have no .venv.", digest="a1")
    vault.codex_says(
        "Linked checkout build failure", "Builds fail in a linked checkout.", digest="b1"
    )

    result = await vault.pass_over()

    notes = store.list_notes(_PARTITION)
    assert result.opened == 2 and len(notes) == 2
    assert sorted(len(n.origins) for n in notes) == [1, 1]
    assert {n.body.strip() for n in notes} == {
        "This repo's worktrees have no .venv.",
        "Builds fail in a linked checkout.",
    }


@pytest.mark.asyncio
async def test_neither_raw_entry_is_modified_or_deleted_by_the_pass(vault: _Vault) -> None:
    vault.claude_says("A", "Claude Code's own words.", digest="a1")
    vault.codex_says("B", "Codex's own words.", digest="b1")
    await vault.service().aggregate()
    before = {
        str(p): (p.read_bytes(), p.stat().st_mtime)
        for p in sorted(paths.raw_dir(_PARTITION).iterdir())
    }

    await vault.pass_over()

    after = {
        str(p): (p.read_bytes(), p.stat().st_mtime)
        for p in sorted(paths.raw_dir(_PARTITION).iterdir())
    }
    assert after == before
    assert len(list_raw_entries(_PARTITION)) == 2


# --- an agent's merge stays done --------------------------------------------


@pytest.mark.asyncio
async def test_a_merge_done_by_origins_and_a_deleted_file_is_not_undone(vault: _Vault) -> None:
    vault.claude_says("Worktree has no .venv", "Worktrees have no .venv.", digest="a1")
    vault.codex_says("Linked checkout failure", "Builds fail in a linked checkout.", digest="b1")
    await vault.pass_over()
    first, second = sorted(store.list_notes(_PARTITION), key=lambda n: n.slug)
    # What the tidying agent does: the survivor takes the merged note's origins.
    store.write_note(
        type(first)(**{**first.__dict__, "origins": (*first.origins, *second.origins)})
    )
    store.delete_note(_PARTITION, second.slug)

    again = await vault.pass_over()

    assert (again.opened, again.retired) == (0, 0)
    assert [n.slug for n in store.list_notes(_PARTITION)] == [first.slug]
    assert store.read_retired(_PARTITION) == ()


# --- an edited note is the note ---------------------------------------------


def _edit(slug: str, body: str) -> None:
    fingerprint = note_edit.note_fingerprint(_PARTITION, slug)
    note_edit.save_body(
        _PARTITION, slug, body, expected_fingerprint=fingerprint, stamp="2026-10-04T00:00:00+00:00"
    )


@pytest.mark.asyncio
async def test_a_note_a_later_pass_leaves_alone_keeps_the_edited_text_byte_for_byte(
    vault: _Vault,
) -> None:
    vault.codex_says("Daemon restart", "Restart with coffer daemon stop/start.", digest="b1")
    await vault.pass_over()
    _edit("daemon-restart", "A person's edit.")
    path = paths.note_path(_PARTITION, "daemon-restart")
    edited = path.read_bytes()

    vault.claude_says("Unrelated", "Something about another subject.", digest="a2")
    await vault.pass_over()

    assert path.read_bytes() == edited
    assert len(store.list_notes(_PARTITION)) == 2


# --- a retirement sticks -----------------------------------------------------


async def _retire_one(vault: _Vault) -> None:
    """Open a note, then let an agent mark it retired."""
    vault.codex_says("The mechanism shipped", "Session injection shipped in July.", digest="b1")
    await vault.pass_over()
    note = store.read_note(_PARTITION, "the-mechanism-shipped")
    store.write_note(
        type(note)(
            **{
                **note.__dict__,
                "retired": "Removed in September.\n\n---\n\nSee the September rewrite.",
                "replaced_by": "session-injection-removed",
            }
        )
    )
    vault.claude_says("Session injection removed", "It was removed in September.", digest="a2")
    await vault.pass_over()


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="a retired note leaves the index and stays out")
async def test_a_marked_notes_file_leaves_notes_and_its_record_names_what_replaced_it(
    vault: _Vault,
) -> None:
    await _retire_one(vault)

    assert not paths.note_path(_PARTITION, "the-mechanism-shipped").exists()
    assert [n.slug for n in store.list_notes(_PARTITION)] == ["session-injection-removed"]

    (record,) = store.read_retired(_PARTITION)
    assert record.slug == "the-mechanism-shipped"
    assert record.replaced_by == "session-injection-removed"
    assert len(record.entry_ids) == 1
    # A reason may be prose, horizontal rule and all — and it must round-trip,
    # or the exclusion list comes back empty and every retirement is undone.
    assert record.reason.startswith("Removed in September.")
    assert "---" in record.reason


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="a retired note leaves the index and stays out")
async def test_no_index_line_mentions_a_retired_note(vault: _Vault) -> None:
    await _retire_one(vault)

    index = store.read_index(_PARTITION)
    assert "the-mechanism-shipped.md" not in index
    assert "session-injection-removed.md" in index


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="a retired note leaves the index and stays out")
async def test_a_second_pass_over_unchanged_sources_does_not_re_open_it(vault: _Vault) -> None:
    """The mechanism, not a nicety: the material the note was built from still
    sits in the agent's own memory, so without ``RETIRED.md`` as input the
    next pass re-imports what the last one removed."""
    await _retire_one(vault)

    service = vault.service()
    result = await service.aggregate()
    assert result.sources_skipped == 2 and result.sources_read == 0
    distilled = await service.distil(vault.resources.uid_of(KIND_MEMORY, _PARTITION))

    assert (distilled.opened, distilled.retired) == (0, 0)
    assert [n.slug for n in store.list_notes(_PARTITION)] == ["session-injection-removed"]
    assert not paths.note_path(_PARTITION, "the-mechanism-shipped").exists()
    assert [r.slug for r in store.read_retired(_PARTITION)] == ["the-mechanism-shipped"]


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="a retired note leaves the index and stays out")
async def test_a_retired_note_reaches_neither_delivery_nor_a_search_of_the_notes(
    vault: _Vault,
) -> None:
    """An agent finds a note by searching ``<memory root>/*/notes/`` itself, and a
    retirement takes the file out of ``notes/``, so the search cannot find it."""
    await _retire_one(vault)
    service = vault.service()

    composed = await compose_context(service, cwd=str(vault.repository))
    matches = [
        path
        for path in sorted(paths.memory_root().glob("*/notes/*.md"))
        if "session injection shipped" in path.read_text(encoding="utf-8").lower()
    ]

    assert composed.partition == _PARTITION
    assert "the-mechanism-shipped.md" not in composed.text
    assert "session-injection-removed.md" in composed.text
    assert matches == []


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="no memory path calls a model")
async def test_a_distil_pass_and_the_session_context_never_reach_a_model(
    vault: _Vault, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The two ways a model is reached from here — an HTTP call to a connection
    and an agent child process — are rigged to fail the test."""

    def _forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("a memory path called a model")

    monkeypatch.setattr(httpx.AsyncClient, "send", _forbidden)
    monkeypatch.setattr(httpx.Client, "send", _forbidden)
    monkeypatch.setattr("asyncio.create_subprocess_exec", _forbidden)
    vault.claude_says("Worktree has no .venv", "Worktrees have no .venv.", digest="a1")

    await vault.pass_over()
    composed = await compose_context(vault.service(), cwd=str(vault.repository))

    assert composed.partition == _PARTITION
    assert "worktree-has-no-venv.md" in composed.text


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="memory", scenario="nothing tidies a partition unattended")
async def test_the_workers_leave_near_duplicate_notes_exactly_as_distil_wrote_them(
    vault: _Vault,
) -> None:
    vault.claude_says("Worktree has no .venv", "This repo's worktrees have no .venv.", digest="a1")
    vault.codex_says("Linked checkout has no .venv", "A linked checkout has no .venv.", digest="b1")
    await vault.pass_over()
    notes_dir = paths.notes_dir(_PARTITION)
    before = {p.name: p.read_bytes() for p in notes_dir.glob("*.md")}
    assert len(before) == 2

    service = vault.service()
    uid = vault.resources.uid_of(KIND_MEMORY, _PARTITION)
    audit_events: list[str] = []

    async def distil(partition_uid: str) -> None:
        await service.distil(partition_uid, actor=WORKER_ACTOR)
        audit_events.append(partition_uid)

    async def partitions() -> list[str]:
        return [uid]

    worker = DistilWorker(distil=distil, list_partitions=partitions)
    for _ in range(3):  # several intervals, and no person chooses Tidy
        await service.aggregate()
        await worker.run_once()

    assert audit_events == [uid, uid, uid]
    assert {p.name: p.read_bytes() for p in notes_dir.glob("*.md")} == before
    assert store.read_retired(_PARTITION) == ()
