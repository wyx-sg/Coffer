"""One pass over the two REAL readers, a real repository and the real store.

This is the seam the unit tier does not cover: the readers are the actual
``ClaudeCodeMemoryReader`` and ``CodexMemoryReader`` parsing realistic fixture
trees, the repository is a real ``git init``, and what comes out is real files
under ``COFFER_MEMORY_ROOT``.

The test that matters most here is the read-only one. **Coffer never writes an
agent's native memory** (FR-002) — that is the prohibition
[Aggregate Agent Memory](../../../../docs/decisions/aggregate-agent-memory-never-write-it.md)
records and the load-bearing constraint of the whole design, so a full pass is
bracketed by a snapshot of every file's **bytes and modification time** under
both config directories.
"""

from __future__ import annotations

import pathlib

import pytest

from coffer.application.memory.index import index_line
from coffer.application.memory.service import KIND_MEMORY, MemoryService
from coffer.domain.memory.note import TYPE_PROJECT, TYPE_USER, Note, Origin
from coffer.domain.resource import ResourceRef
from coffer.infrastructure.memory import store
from coffer.infrastructure.memory.raw_store import list_raw_entries
from coffer.infrastructure.memory.readers import ClaudeCodeMemoryReader, CodexMemoryReader
from tests.integration.memory.conftest import (
    FakeAudit,
    FakeResources,
    agent_source_resolver,
    claude_code_config,
    codex_config,
    init_repository,
)

_CC_PREFERENCE = """---
name: feedback-worktree-development
description: Always develop in a git worktree
metadata:
  node_type: memory
  type: feedback
---

Multiple parallel sessions share the repo — always work in a worktree.
"""

_CC_PROJECT = """---
name: python-lockfile
description: Dependencies are locked with uv
metadata:
  node_type: memory
  type: project
---

Run `uv sync --frozen` in this project; a plain `pip install` drifts.
"""

_CODEX_MEMORY = """# Task Group: coffer daemon restart and port drift

applies_to: cwd={project_root}; reuse_rule=recheck

## Task 1: restart, success

### rollout_summary_files

- rollout-2026-09-01.md

## Reusable knowledge

- the coffer daemon restarts with `coffer daemon stop/start`. [Task 1]

## Failures and how to do differently

- Symptom: shim could not connect. Fix: kill the stale shim. [Task 1]
"""

_CODEX_SUMMARY = """v1

## User Profile

Works primarily on the Coffer project and prefers concise replies.

## User preferences

- Always ask before merging a pull request. [ad-hoc]

## What's in Memory

### {project_root}

- coffer daemon restart port drift: `coffer daemon`, `port drift`
  - desc: restarting the daemon
  - learnings: the shim pins the old port

## General Tips

- this roll-up is never read as entries.
"""


def _snapshot(root: pathlib.Path) -> dict[str, tuple[bytes, float]]:
    return {
        str(p): (p.read_bytes(), p.stat().st_mtime) for p in sorted(root.rglob("*")) if p.is_file()
    }


@pytest.fixture
def vault(tmp_path: pathlib.Path):  # type: ignore[no-untyped-def]
    project_root = init_repository(
        tmp_path / "home" / "dev" / "coffer", remote="git@github.com:owner/coffer.git"
    )
    claude_dir = claude_code_config(
        tmp_path / "claude",
        project_root,
        {
            "feedback-worktree-development.md": _CC_PREFERENCE,
            "python-lockfile.md": _CC_PROJECT,
            "MEMORY.md": "# Memory\n\n- a roll-up Claude Code regenerates\n",
        },
    )
    codex_dir = codex_config(
        tmp_path / "codex",
        _CODEX_MEMORY.format(project_root=project_root),
        _CODEX_SUMMARY.format(project_root=project_root),
    )

    resources = FakeResources()
    resources.add_agent("claude-code", "claude_code", str(claude_dir))
    resources.add_agent("codex", "codex", str(codex_dir))
    service = MemoryService(
        resources=resources,  # type: ignore[arg-type]
        audit=FakeAudit(),  # type: ignore[arg-type]
        agent_source_resolver=agent_source_resolver,
        readers={"claude_code": ClaudeCodeMemoryReader(), "codex": CodexMemoryReader()},
    )
    return {
        "service": service,
        "resources": resources,
        "project_root": project_root,
        "claude_dir": claude_dir,
        "codex_dir": codex_dir,
    }


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="aggregation never modifies an agent's native memory files"
)
async def test_a_full_pass_leaves_both_agents_files_byte_identical_and_untouched(vault) -> None:  # type: ignore[no-untyped-def]
    before_claude = _snapshot(vault["claude_dir"])
    before_codex = _snapshot(vault["codex_dir"])
    assert before_claude and before_codex  # the snapshot actually saw the fixtures

    result = await vault["service"].aggregate()

    assert result.entries_written > 0  # both agents really were read
    assert _snapshot(vault["claude_dir"]) == before_claude
    assert _snapshot(vault["codex_dir"]) == before_codex
    # Nothing created, nothing moved, nothing deleted either.
    assert sorted(p.name for p in (vault["codex_dir"] / "memories").iterdir()) == [
        "MEMORY.md",
        "memory_summary.md",
    ]


@pytest.mark.asyncio
async def test_both_agents_material_lands_in_the_repositorys_partition(vault) -> None:  # type: ignore[no-untyped-def]
    result = await vault["service"].aggregate()

    assert sorted(result.partitions) == ["coffer", "global"]
    entries = list_raw_entries("coffer")
    assert {e.agent for e in entries} == {"claude-code", "codex"}
    assert any("uv sync --frozen" in e.entry.body for e in entries)
    assert any("coffer daemon stop/start" in e.entry.body for e in entries)


@pytest.mark.asyncio
async def test_what_is_about_the_person_lands_in_global_whichever_agent_said_it(vault) -> None:  # type: ignore[no-untyped-def]
    await vault["service"].aggregate()

    titles = {e.entry.title for e in list_raw_entries("global")}
    assert "feedback-worktree-development" in titles  # Claude Code's `feedback`
    assert "User Profile" in titles  # Codex's profile
    assert "Always ask before merging a pull request" in titles


@pytest.mark.asyncio
async def test_neither_agents_own_roll_up_is_read_as_material(vault) -> None:  # type: ignore[no-untyped-def]
    await vault["service"].aggregate()

    bodies = "\n".join(e.entry.body for p in ("coffer", "global") for e in list_raw_entries(p))
    assert "a roll-up Claude Code regenerates" not in bodies
    assert "this roll-up is never read as entries" not in bodies
    assert "rollout-2026-09-01.md" not in bodies


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory",
    scenario="a Codex task group becomes raw entries carrying its own search terms",
)
async def test_codexs_search_terms_reach_the_entry_and_the_index_line(vault) -> None:  # type: ignore[no-untyped-def]
    """FR-004 carries the source's own terms; FR-029 has the index line state
    them, so the next agent does not have to guess a word."""
    await vault["service"].aggregate()

    entries = [e for e in list_raw_entries("coffer") if e.agent == "codex"]
    assert entries
    assert all(e.entry.search_terms == ("coffer daemon", "port drift") for e in entries)

    note = Note(
        slug="daemon-restart",
        title="Daemon restart",
        description="restart with coffer daemon stop/start",
        type=TYPE_PROJECT,
        body="b",
        partition="coffer",
        origins=(entries[0].origin,),
        search_terms=entries[0].entry.search_terms,
    )
    assert index_line(note).endswith(" · look up: coffer daemon, port drift")


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory",
    scenario="a partition is registered as a resource scoped to the agents it came from",
)
async def test_the_partition_is_scoped_to_both_agents_it_was_aggregated_from(vault) -> None:  # type: ignore[no-untyped-def]
    await vault["service"].aggregate()

    row = await vault["resources"].get(ResourceRef(KIND_MEMORY, "coffer"))
    assert row.scope is not None
    assert set(row.scope.agents or []) == {"claude-code", "codex"}
    assert row.config["repository_path"] == str(vault["project_root"].resolve())


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="an agent whose native memory shape is unreadable degrades loudly"
)
async def test_a_malformed_file_in_one_agent_leaves_the_others_material_and_the_notes_standing(
    vault,  # type: ignore[no-untyped-def]
) -> None:
    """SC-006, with a real reader hitting a real broken file.

    A previously distilled note must be left standing: a reader broken by an
    agent's format change may not empty that agent's contribution, and must
    not touch anyone else's.
    """
    broken = (
        vault["claude_dir"]
        / "projects"
        / next((vault["claude_dir"] / "projects").iterdir()).name
        / "memory"
        / "broken.md"
    )
    broken.write_text("no frontmatter fence at all\n", encoding="utf-8")
    store.write_note(
        Note(
            slug="standing",
            title="Standing",
            description="written by an earlier pass",
            type=TYPE_USER,
            body="body",
            partition="global",
            origins=(Origin(agent="codex", native_path="/old.md", anchor="x"),),
        )
    )

    result = await vault["service"].aggregate()

    assert len(result.failures) == 1
    failure = result.failures[0]
    assert failure.agent == "claude-code"
    assert failure.path == str(broken)
    assert "frontmatter" in failure.reason

    # Everything else completed: the other agent, and the rest of this one's.
    assert {e.agent for e in list_raw_entries("coffer")} == {"claude-code", "codex"}
    assert [n.slug for n in store.list_notes("global")] == ["standing"]


@pytest.mark.asyncio
async def test_a_second_pass_over_untouched_agents_reads_nothing_and_changes_nothing(
    vault,  # type: ignore[no-untyped-def]
) -> None:
    await vault["service"].aggregate()
    before = {
        p: {e.entry_id: e.entry.body for e in list_raw_entries(p)} for p in store.list_partitions()
    }

    second = await vault["service"].aggregate()

    assert second.sources_read == 0
    # Two Claude Code entry files (its own MEMORY.md is never a source) and
    # both of Codex's two.
    assert second.sources_skipped == 4
    assert {
        p: {e.entry_id: e.entry.body for e in list_raw_entries(p)} for p in store.list_partitions()
    } == before
