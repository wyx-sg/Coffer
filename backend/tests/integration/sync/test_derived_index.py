"""Derived index files (e.g. memory's MEMORY.md) must not cause sync conflicts.

MEMORY.md is regenerated from the per-fact ``*.md`` files, so two machines with
different memories produce different MEMORY.md — a spurious same-path conflict.
Sync excludes such derived indexes from the mirror and regenerates them on
import from the (merged) fact files.
"""

from __future__ import annotations

import subprocess

import pytest
import pytest_asyncio

from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.importer import SyncImporter
from coffer.domain.sync.models import SyncStatus
from coffer.infrastructure.sync.workspace import DERIVED_INDEX_NAMES, Workspace

from .test_two_machine_sync import _make_machine


@pytest_asyncio.fixture
async def remote(tmp_path):  # type: ignore[no-untyped-def]
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    return bare


def _wire_memory(machine, store_dir, tmp_root):  # type: ignore[no-untyped-def]
    """Point a machine's sync at a memory tree + regenerate-index post-import hook."""
    from coffer.infrastructure.memory.files import regenerate_memory_index
    from coffer.infrastructure.sync.credentials import CredentialSyncAdapter

    cred = CredentialSyncAdapter(machine.db_path, machine.master_key)
    # Reuse the machine's own git working tree (machine.root/"ws") so the
    # exporter writes where GitRepo operates.
    ws = Workspace(machine.root / "ws", trees=[("memory", store_dir)])

    async def regen() -> None:
        regenerate_memory_index(store_dir)

    machine.service._exporter = SyncExporter(machine.resources, cred, ws)
    machine.service._importer = SyncImporter(machine.resources, cred, ws, post_import=regen)


@pytest.mark.acceptance(spec="010-sync", scenario="only shared state syncs")
async def test_divergent_memory_index_does_not_conflict(tmp_path, remote) -> None:  # type: ignore[no-untyped-def]
    a = await _make_machine("A", tmp_path / "A", remote, create_key=True)
    a_mem = tmp_path / "A" / "mem"
    a_mem.mkdir(parents=True)
    (a_mem / "fact-a.md").write_text("---\nname: a\ndescription: A's fact\n---\nbody A\n")
    (a_mem / "MEMORY.md").write_text("# Memory\n- [a](fact-a.md) — A's fact\n")
    _wire_memory(a, a_mem, tmp_path)
    assert (await a.service.run()).status is SyncStatus.CLEAN

    b = await _make_machine("B", tmp_path / "B", remote, create_key=True)
    b_mem = tmp_path / "B" / "mem"
    b_mem.mkdir(parents=True)
    (b_mem / "fact-b.md").write_text("---\nname: b\ndescription: B's fact\n---\nbody B\n")
    (b_mem / "MEMORY.md").write_text("# Memory\n- [b](fact-b.md) — B's fact\n")
    _wire_memory(b, b_mem, tmp_path)

    # Divergent memories — must NOT conflict on the regenerated index.
    state = await b.service.run()
    assert state.status is SyncStatus.CLEAN, state.conflict_paths

    # Both fact files converged on B...
    assert (b_mem / "fact-a.md").exists()
    assert (b_mem / "fact-b.md").exists()
    # ...and MEMORY.md was regenerated to list both, from the merged facts.
    index = (b_mem / "MEMORY.md").read_text()
    assert "fact-a.md" in index and "fact-b.md" in index


def test_memory_index_excluded_from_mirror_constant() -> None:
    assert "MEMORY.md" in DERIVED_INDEX_NAMES
