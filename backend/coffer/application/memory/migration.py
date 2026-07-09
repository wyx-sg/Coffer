"""One-time adoption of legacy path-derived memory stores (spec 007 FR-004a).

Pre-portable-identity stores are keyed by a hash of the absolute git-root
path, which differs per machine. On first resolve under the portable
(remote-URL-derived) id, the legacy store is adopted: files move, the resource
is re-registered under the new name, the root mapping and display label carry
over, and the old resource is deleted (propagating the rename through sync
tombstones; its on_delete purges the stale index rows — the dir is already
gone and that teardown is tolerant).
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from coffer.application.memory.scope import KIND_MEMORY, project_store_name
from coffer.application.resource_service import ResourceService
from coffer.domain.resource import ResourceRef


class _RootsPort(Protocol):
    async def get(self, store_name: str) -> str | None: ...
    async def set(self, store_name: str, project_root: str) -> None: ...


class _LabelsPort(Protocol):
    async def get(self, store_name: str) -> str | None: ...
    async def set(self, store_name: str, label: str) -> None: ...


def make_store_migrator(
    resources: ResourceService,
    project_roots: _RootsPort,
    labels: _LabelsPort,
    store_dir: Callable[[str], Path],
) -> Callable[[str, str], Awaitable[None]]:
    async def migrate_store(legacy_id: str, new_id: str) -> None:
        old_name, new_name = project_store_name(legacy_id), project_store_name(new_id)
        old_dir, new_dir = store_dir(legacy_id), store_dir(new_id)
        if old_dir.exists() and not new_dir.exists():
            await asyncio.to_thread(shutil.move, str(old_dir), str(new_dir))
        old_res = await resources.get(ResourceRef(KIND_MEMORY, old_name))
        await resources.register(
            KIND_MEMORY, new_name, dict(old_res.config), "system", allow_lifecycle_kind=True
        )
        root = await project_roots.get(old_name)
        if root:
            await project_roots.set(new_name, root)
        label = await labels.get(old_name)
        if label:
            await labels.set(new_name, label)
        await resources.delete(ResourceRef(KIND_MEMORY, old_name), "system")

    return migrate_store
