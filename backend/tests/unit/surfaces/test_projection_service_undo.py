"""Unit: ProjectionService failure semantics (FR-020).

A failed native undo must KEEP the binding row and propagate (deleting the row
would orphan the symlink/managed block forever); store-level teardown logs and
deletes anyway because the store itself is going away.
"""

from __future__ import annotations

import pytest

from coffer.application.agent.projection import ProjectionEngine
from coffer.surfaces.http.projection_service import ProjectionService

pytestmark = pytest.mark.asyncio


class _Binding:
    def __init__(self) -> None:
        self.store_name = "global"
        self.agent_ref = "codex-x"
        self.projection_mode = "RENDER"
        self.target_path = "/tmp/AGENTS.md"
        self.native_memory_disabled = True


class _Bindings:
    def __init__(self) -> None:
        self.rows = {("global", "codex-x"): _Binding()}
        self.deleted: list[tuple[str, str]] = []

    async def get(self, store_name: str, agent_ref: str):
        return self.rows.get((store_name, agent_ref))

    async def list_for_store(self, store_name: str):
        return [b for (s, _a), b in self.rows.items() if s == store_name]

    async def delete(self, store_name: str, agent_ref: str) -> bool:
        self.deleted.append((store_name, agent_ref))
        return self.rows.pop((store_name, agent_ref), None) is not None


class _FailingFs:
    def remove_symlink(self, *, link_path):  # type: ignore[no-untyped-def]
        raise OSError("permission denied")

    def strip_managed_block(self, **_kw):  # type: ignore[no-untyped-def]
        raise OSError("permission denied")


async def test_failed_native_undo_keeps_the_binding_row() -> None:
    bindings = _Bindings()
    svc = ProjectionService(
        memory=None,  # type: ignore[arg-type]  # not reached on this path
        agents=None,  # type: ignore[arg-type]
        engine=ProjectionEngine(_FailingFs()),  # type: ignore[arg-type]
        bindings=bindings,  # type: ignore[arg-type]
    )
    with pytest.raises(OSError):
        await svc.remove(store_name="global", agent_ref="codex-x")
    # The binding row survives so the orphaned native target stays addressable.
    assert bindings.deleted == []
    assert ("global", "codex-x") in bindings.rows


async def test_store_teardown_deletes_binding_even_if_undo_fails() -> None:
    bindings = _Bindings()
    svc = ProjectionService(
        memory=None,  # type: ignore[arg-type]
        agents=None,  # type: ignore[arg-type]
        engine=ProjectionEngine(_FailingFs()),  # type: ignore[arg-type]
        bindings=bindings,  # type: ignore[arg-type]
    )
    await svc.remove_all_for_store(store_name="global")
    # The store is going away: the row must not dangle.
    assert bindings.deleted == [("global", "codex-x")]
