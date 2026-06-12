"""Composition-root wiring for memory projection (spec 007).

Lives outside the per-kind subpackages so it may import BOTH the memory kind and
the agent kind (the cross-kind contracts fence the kinds off from each other,
not the composition root). Builds the :class:`ProjectionService` from the
already-wired ``MemoryService`` + ``AgentService`` + a binding repo, installs it
on the projection routes, and registers the memory ``on_change`` hook so
established projections re-render on every memory write.
"""

from __future__ import annotations

import logging
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

    from coffer.application.audit_service import AuditService
    from coffer.application.memory.service import MemoryService
    from coffer.domain.resource import ResourceRef

_logger = logging.getLogger(__name__)


def wire_projection(
    app: FastAPI,
    sm: object,
    memory_service: MemoryService,
    audit: AuditService | None = None,
) -> ProjectionService:
    """Build + install the projection service and the memory change hook."""
    bindings = ProjectionBindingRepo(sm)  # type: ignore[arg-type]
    engine = ProjectionEngine(ProjectionFsAdapter())

    async def _store_for_root(project_root: str) -> str:
        """The memory-store name Coffer keys ``project_root`` by (provisioning if
        needed). Resolves it the SAME way a ``remember`` from that directory
        would — by git-root — so a takeover and later writes land in one store.
        A non-git project root has no git-keyed store, so fall back to a store
        keyed by the root path itself."""
        from coffer.application.memory.scope import project_store_name
        from coffer.application.memory.stores import store_name_for
        from coffer.domain.errors import ScopeUnresolved
        from coffer.domain.memory.scope import MemoryScope
        from coffer.infrastructure.memory.scope_fs import project_ulid

        try:
            resolved = await memory_service.resolve_scope(
                scope=MemoryScope.PROJECT, cwd=project_root
            )
            return store_name_for(resolved)
        except ScopeUnresolved:
            store = project_store_name(project_ulid(project_root))
            await memory_service.ensure_store(store)
            return store

    service = ProjectionService(
        memory=memory_service,
        agents=get_agent_service(),
        engine=engine,
        bindings=bindings,
        audit=audit,
        store_for_root=_store_for_root,
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
        try:
            await service.remove_all_for_store(store_name=ref.name)
        except Exception:
            _logger.warning(
                "projection.on_delete.cleanup_failed",
                extra={"store": ref.name},
                exc_info=True,
            )
        if inner is not None:
            result = inner(ref)
            if result is not None:
                await result

    app.state.kinds["memory"] = replace(kind, on_delete=_on_delete)
