"""Composition root for the sync service (spec 010).

Builds the sync object graph (git transport, workspace IO, ciphertext
credential adapter, export/import, service) over the same session_maker and
master-key manager the rest of the daemon uses, registers the HTTP service
singleton, and returns the auto-sync worker for the lifespan to start.
"""

from __future__ import annotations

import asyncio
import contextlib
import pathlib
import platform

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.sync.config_service import SyncConfigService
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.importer import SyncImporter
from coffer.application.sync.service import SyncService
from coffer.application.sync.worker import SyncWorker
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.infrastructure.memory.files import regenerate_memory_index
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter
from coffer.infrastructure.sync.git_repo import GitRepo
from coffer.infrastructure.sync.paths import memory_root, sync_root
from coffer.infrastructure.sync.persistence import (
    SqlAlchemySyncConfigRepo,
    SqlAlchemySyncStateRepo,
)
from coffer.infrastructure.sync.workspace import Workspace
from coffer.surfaces.http.sync_routes import set_sync_service


async def _regenerate_memory_indexes() -> None:
    """Rebuild each memory store's ``MEMORY.md`` from the just-synced fact files.

    Derived indexes are excluded from the sync mirror (they differ per machine
    and would conflict), so they must be regenerated after import.
    """
    root = memory_root()
    store_dirs: list[pathlib.Path] = []
    if (root / "global").exists():
        store_dirs.append(root / "global")
    projects = root / "projects"
    if projects.is_dir():
        store_dirs.extend(d for d in projects.iterdir() if d.is_dir())
    for store_dir in store_dirs:
        await asyncio.to_thread(regenerate_memory_index, store_dir)


def wire_sync(
    resource_svc: ResourceService,
    audit: AuditService,
    sm: async_sessionmaker,  # type: ignore[type-arg]
    db_path: pathlib.Path,
    master_key: MasterKeyManager,
) -> SyncWorker:
    root = sync_root()
    cred_sync = CredentialSyncAdapter(db_path, master_key)
    workspace = Workspace(root)
    git = GitRepo(root)
    config_svc = SyncConfigService(SqlAlchemySyncConfigRepo(sm), SqlAlchemySyncStateRepo(sm), audit)
    service = SyncService(
        config=config_svc,
        git=git,
        exporter=SyncExporter(resource_svc, cred_sync, workspace),
        importer=SyncImporter(
            resource_svc, cred_sync, workspace, post_import=_regenerate_memory_indexes
        ),
        credentials=cred_sync,
        master_key=master_key,
        audit=audit,
        machine_id=platform.node() or "coffer",
    )
    set_sync_service(service)
    return SyncWorker(service, config_svc)


def start_sync(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: async_sessionmaker,  # type: ignore[type-arg]
    db_path: pathlib.Path,
    master_key: MasterKeyManager,
) -> None:
    """Wire sync and start its (initially inert) auto-sync worker task."""
    worker = wire_sync(resource_svc, audit, sm, db_path, master_key)
    app.state.sync_worker = worker
    app.state.sync_worker_task = asyncio.create_task(worker.run())


async def stop_sync(app: FastAPI) -> None:
    worker = getattr(app.state, "sync_worker", None)
    task = getattr(app.state, "sync_worker_task", None)
    if worker is not None:
        worker.stop()
    if task is not None:
        task.cancel()
        with contextlib.suppress(BaseException):
            await asyncio.wait_for(task, timeout=2.0)
