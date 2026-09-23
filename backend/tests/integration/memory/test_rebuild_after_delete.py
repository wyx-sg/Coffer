"""Delete the tree, re-sync, get an equivalent partition back.

See "Keep the memory tree derived and local".

Everything under ``~/.coffer/memory/`` is derived, which is what makes it safe
to rewrite aggressively — but only if it actually comes back. The trap is the
source-state cache: **a digest match says the *source* is unchanged, not that
the entries it produced are still on disk.** So the scenario deliberately
leaves ``.source_state.json`` behind, which is the case a naive skip gets
wrong and a user would experience as a partition that silently stays empty
forever.

What comes back is *equivalent*, not identical. ``.raw/`` reproduces exactly —
same entry ids, same words, because they are the agents' own and only the
capture time moves. ``notes/`` covers the same subjects from the same sources
without being required to match the wording, because the notes are Coffer's
own distillation rather than a copy.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

from coffer.application.memory.service import KIND_MEMORY, MemoryService
from coffer.infrastructure.memory import paths, source_state, store
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
from tests.unit.memory.conftest import ScriptedCompletion, StubModelSelector

_PARTITION = "coffer"

_CC_PROJECT = """---
name: python-lockfile
description: Dependencies are locked with uv
metadata:
  type: project
---

Run `uv sync --frozen`; a plain `pip install` drifts.
"""

_CODEX_MEMORY = """# Task Group: coffer daemon

applies_to: cwd={project_root}

## Reusable knowledge

- the coffer daemon restarts with `coffer daemon stop/start`. [Task 1]
"""


def _route(*items: dict[str, Any]) -> str:
    return json.dumps({"actions": list(items)})


def _write(title: str, description: str, body: str) -> str:
    return json.dumps({"title": title, "description": description, "body": body})


def _snapshot_raw(partition: str) -> dict[str, tuple[str, str, str]]:
    """Each raw entry by id, with the agents' own words.

    Everything except ``captured_at`` has to come back the same: the entry id
    is the identity a note's provenance points at, and the body is the whole
    of what ``.raw/`` is for. ``captured_at`` is the time Coffer read it, which
    a rebuild legitimately moves.
    """
    return {e.entry_id: (e.agent, e.entry.title, e.entry.body) for e in list_raw_entries(partition)}


def _subjects() -> dict[str, tuple[str, ...]]:
    """Each note by the raw entries it was built from — the identity that has
    to survive a rebuild, as opposed to the prose, which does not."""
    return {n.slug: tuple(sorted(o.key for o in n.origins)) for n in store.list_notes(_PARTITION)}


@pytest.fixture
def vault(tmp_path: pathlib.Path):  # type: ignore[no-untyped-def]
    project_root = init_repository(tmp_path / "home" / "dev" / "coffer")
    claude_dir = claude_code_config(
        tmp_path / "claude", project_root, {"python-lockfile.md": _CC_PROJECT}
    )
    codex_dir = codex_config(tmp_path / "codex", _CODEX_MEMORY.format(project_root=project_root))
    resources = FakeResources()
    resources.add_agent("claude-code", "claude_code", str(claude_dir))
    resources.add_agent("codex", "codex", str(codex_dir))
    completion = ScriptedCompletion([])

    def service() -> MemoryService:
        return MemoryService(
            resources=resources,  # type: ignore[arg-type]
            audit=FakeAudit(),  # type: ignore[arg-type]
            agent_source_resolver=agent_source_resolver,
            readers={"claude_code": ClaudeCodeMemoryReader(), "codex": CodexMemoryReader()},
            completion=completion,  # type: ignore[arg-type]
            model_selector=StubModelSelector(),
        )

    return {
        "service": service,
        "resources": resources,
        "completion": completion,
        "project_root": project_root,
    }


async def _aggregate_then_distil(vault, *, wording: str) -> None:  # type: ignore[no-untyped-def]
    """One full cycle. The routing answer names entry ids, which only exist
    once aggregation has written them — so the script is built between the two
    halves rather than up front."""
    service = vault["service"]()
    await service.aggregate()
    vault["completion"]._responses.extend(_answers(wording=wording))
    # Resolved after aggregation: the partition's row (and so its uid) is what
    # that half creates.
    await service.distil(vault["resources"].uid_of(KIND_MEMORY, _PARTITION))


def _answers(*, wording: str) -> list[str]:
    ids = sorted(e.entry_id for e in list_raw_entries(_PARTITION))
    assert len(ids) == 2
    return [
        _route(
            {"entry": ids[0], "action": "open", "title": "The lockfile rule", "type": "project"},
            {"entry": ids[1], "action": "open", "title": "Daemon restart", "type": "project"},
        ),
        # One writing request per touched note, in slug order.
        _write("Daemon restart", f"{wording}: restart the daemon", f"{wording} body one"),
        _write("The lockfile rule", f"{wording}: lock with uv", f"{wording} body two"),
    ]


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="deleting the memory tree and re-syncing reproduces an equivalent set"
)
async def test_deleting_the_tree_with_the_digest_cache_left_behind_rebuilds_it(vault) -> None:  # type: ignore[no-untyped-def]
    await _aggregate_then_distil(vault, wording="first")

    raw_before = _snapshot_raw(_PARTITION)
    subjects_before = _subjects()
    bodies_before = {n.slug: n.body for n in store.list_notes(_PARTITION)}
    assert len(raw_before) == 2
    assert len(subjects_before) == 2

    # Delete the tree by hand, and leave the cache behind on purpose.
    for partition in store.list_partitions():
        store.delete_partition(partition)
    assert store.list_partitions() == ()
    assert not paths.partition_dir(_PARTITION).exists()
    assert source_state.load(), "the digest cache is deliberately still here"

    await _aggregate_then_distil(vault, wording="second")

    assert _snapshot_raw(_PARTITION) == raw_before  # the same entries, verbatim
    assert _subjects() == subjects_before  # the same subjects, from the same sources
    index = store.read_index(_PARTITION)
    for slug in subjects_before:
        assert f"`{slug}.md`" in index
    # Equivalent, not identical: the wording is the distillation's, and "Keep the
    # memory tree derived and local" does not require it back.
    assert {n.slug: n.body for n in store.list_notes(_PARTITION)} != bodies_before


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="memory", scenario="deleting the memory tree and re-syncing reproduces an equivalent set"
)
async def test_a_source_whose_entries_are_gone_is_read_again_however_familiar_its_hash(
    vault,  # type: ignore[no-untyped-def]
) -> None:
    service = vault["service"]()
    first = await service.aggregate()
    assert first.sources_read == 2

    skipped = await vault["service"]().aggregate()
    assert (skipped.sources_read, skipped.sources_skipped) == (0, 2)

    store.delete_partition(_PARTITION)
    assert source_state.load()  # unchanged: the cache survives the delete

    rebuilt = await vault["service"]().aggregate()

    assert rebuilt.sources_read == 2
    assert rebuilt.sources_skipped == 0
    assert len(list_raw_entries(_PARTITION)) == 2


@pytest.mark.asyncio
async def test_a_partition_rebuilt_from_scratch_is_registered_again(vault) -> None:  # type: ignore[no-untyped-def]
    service = vault["service"]()
    await service.aggregate()
    summaries = {p.name: p for p in await service.list_partitions()}
    assert summaries[_PARTITION].repository_path

    store.delete_partition(_PARTITION)
    await vault["service"]().aggregate()

    rebuilt = {p.name: p for p in await vault["service"]().list_partitions()}
    assert rebuilt[_PARTITION].repository_path == summaries[_PARTITION].repository_path
    assert rebuilt[_PARTITION].unresolvable is False
