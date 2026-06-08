"""Composition-root wiring for memory projection (spec 007).

Lives outside the per-kind subpackages so it may import BOTH the memory kind and
the agent kind (the cross-kind contracts fence the kinds off from each other,
not the composition root). Builds the :class:`ProjectionService` from the
already-wired ``MemoryService`` + ``AgentService`` + a binding repo, installs it
on the projection routes, and registers the memory ``on_change`` hook so
established projections re-render on every memory write.
"""

from __future__ import annotations

import contextlib
from dataclasses import replace
from typing import TYPE_CHECKING

from coffer.application.agent.projection import ProjectionEngine
from coffer.infrastructure.agent.projection_fs import ProjectionFsAdapter
from coffer.infrastructure.agent.projection_persistence import ProjectionBindingRepo
from coffer.surfaces.http.dependencies import get_agent_service
from coffer.surfaces.http.projection_routes import set_projection_service
from coffer.surfaces.http.projection_service import ProjectionService

if TYPE_CHECKING:
    from fastapi import FastAPI

    from coffer.application.memory.service import MemoryService
    from coffer.domain.resource import ResourceRef


def wire_projection(app: FastAPI, sm: object, memory_service: MemoryService) -> ProjectionService:
    """Build + install the projection service and the memory change hook."""
    bindings = ProjectionBindingRepo(sm)  # type: ignore[arg-type]
    engine = ProjectionEngine(ProjectionFsAdapter())
    service = ProjectionService(
        memory=memory_service,
        agents=get_agent_service(),
        engine=engine,
        bindings=bindings,
    )
    set_projection_service(service)

    async def _on_memory_change(store_name: str) -> None:
        await service.rerender_for_store(store_name=store_name)

    memory_service.set_on_change(_on_memory_change)
    _chain_store_delete_cleanup(app, service)
    app.state.projection_service = service
    return service


def _chain_store_delete_cleanup(app: FastAPI, service: ProjectionService) -> None:
    """Extend the memory kind's ``on_delete`` so deleting a store also tears down
    its projections (native targets + binding rows). The composition root may
    bridge the two kinds; the memory kind itself must not import the agent kind
    (finding #6)."""
    kind = app.state.kinds.get("memory")
    if kind is None:
        return
    inner = kind.on_delete

    async def _on_delete(ref: ResourceRef) -> None:
        # Remove projections first so native symlinks/blocks go before the
        # canonical store dir is rmtree'd by the original cleanup hook.
        with contextlib.suppress(Exception):
            await service.remove_all_for_store(store_name=ref.name)
        if inner is not None:
            result = inner(ref)
            if result is not None:
                await result

    app.state.kinds["memory"] = replace(kind, on_delete=_on_delete)
