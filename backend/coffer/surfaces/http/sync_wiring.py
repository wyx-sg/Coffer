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

from coffer import __version__ as _coffer_version
from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.sync.config_service import SyncConfigService
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.identity import MachineIdentityService
from coffer.application.sync.importer import SyncImporter
from coffer.application.sync.service import SyncService
from coffer.application.sync.worker import SyncWorker
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.infrastructure.knowledge.ids import new_ulid
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter
from coffer.infrastructure.sync.git_repo import GitRepo
from coffer.infrastructure.sync.paths import mirrored_trees, sync_root
from coffer.infrastructure.sync.persistence import (
    SqlAlchemyMachineIdentityRepo,
    SqlAlchemySyncConfigRepo,
    SqlAlchemySyncStateRepo,
    SqlAlchemyTombstoneLedgerRepo,
)
from coffer.infrastructure.sync.watcher import watch_trees
from coffer.infrastructure.sync.workspace import Workspace
from coffer.surfaces.http.sync_routes import set_sync_service


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
    identity = MachineIdentityService(
        SqlAlchemyMachineIdentityRepo(sm),
        audit,
        new_id=new_ulid,
        default_name=lambda: platform.node() or "coffer",
    )
    ledger = SqlAlchemyTombstoneLedgerRepo(sm)
    # Every local deletion lands in the tombstone ledger so it propagates as an
    # explicit workspace tombstone (spec 010: absence alone never deletes).
    # Only the user's own deletions enter the ledger: sync-applied deletions
    # already came FROM the medium, and re-exporting them would cascade-rewrite
    # tombstone provenance across machines.
    resource_svc.add_delete_listener(
        lambda ref, actor: None if actor == "sync" else ledger.record(ref.kind, ref.name)
    )
    service = SyncService(
        config=config_svc,
        git=git,
        exporter=SyncExporter(resource_svc, cred_sync, workspace, ledger),
        importer=SyncImporter(resource_svc, cred_sync, workspace),
        credentials=cred_sync,
        master_key=master_key,
        audit=audit,
        identity=identity,
        workspace=workspace,
        coffer_version=_coffer_version,
    )
    set_sync_service(service)
    worker = SyncWorker(service, config_svc, git)
    # Near-real-time push side (ADR-043): daemon-mediated resource mutations
    # feed the debouncer directly; the file-tree watcher (started in
    # start_sync) catches symlink writes that bypass the daemon.
    resource_svc.add_change_listener(worker.notify_change)
    return worker


def start_sync(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: async_sessionmaker,  # type: ignore[type-arg]
    db_path: pathlib.Path,
    master_key: MasterKeyManager,
) -> None:
    """Wire sync and start its (initially inert) auto-sync worker + watcher."""
    worker = wire_sync(resource_svc, audit, sm, db_path, master_key)
    app.state.sync_worker = worker
    app.state.sync_worker_task = asyncio.create_task(worker.run())
    stop_event = asyncio.Event()
    app.state.sync_watcher_stop = stop_event
    roots = [root for _subdir, root in mirrored_trees()]
    app.state.sync_watcher_task = asyncio.create_task(
        watch_trees(roots, worker.notify_change, stop_event)
    )


async def stop_sync(app: FastAPI) -> None:
    worker = getattr(app.state, "sync_worker", None)
    watcher_stop = getattr(app.state, "sync_watcher_stop", None)
    if worker is not None:
        worker.stop()
    if watcher_stop is not None:
        watcher_stop.set()
    for attr in ("sync_worker_task", "sync_watcher_task"):
        task = getattr(app.state, attr, None)
        if task is not None:
            task.cancel()
            with contextlib.suppress(BaseException):
                await asyncio.wait_for(task, timeout=2.0)
