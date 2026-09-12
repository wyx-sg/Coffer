"""Composition root for the vault export/import service
(spec vault-export-import, ADR: vault-export-import).

Builds the object graph (bundle IO factory, ciphertext credential adapter,
exporter/importer) over the same master-key manager the rest of the daemon
uses and registers the HTTP service singletons.

Export and import run only when the user asks. The backup service built
alongside them acts on demand too, but it is the thing a ``BackupWorker``
drives on a timer, so this module also owns starting and stopping that loop —
the same start/stop pair ``tidy_wiring`` exposes, so ``app.py`` stays a list of
what runs rather than a transcript of how each thing is torn down.
"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Sequence
from typing import Any, NamedTuple

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.application.audit_service import AuditService
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.resource_service import ResourceService
from coffer.application.sync.backup_service import BackupService
from coffer.application.sync.backup_worker import BackupWorker
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.importer import SyncImporter
from coffer.application.sync.ports import (
    BundlePort,
    GitMirrorPort,
    ImportGate,
    PostImportHook,
    SyncedStatePort,
)
from coffer.application.sync.service import SyncService
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.infrastructure.persistence.sync_remote_repo import SqlAlchemySyncRemoteRepo
from coffer.infrastructure.sync.bundle import Bundle
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter
from coffer.infrastructure.sync.git_mirror import GitMirror
from coffer.surfaces.http.sync_routes import set_backup_service, set_sync_service


class SyncWiring(NamedTuple):
    """What the composition root gets back: the on-demand service, and the
    backup service a worker can be started over."""

    sync: SyncService
    backup: BackupService


def wire_sync(
    resource_svc: ResourceService,
    audit: AuditService,
    db_path: pathlib.Path,
    master_key: MasterKeyManager,
    sm: async_sessionmaker,  # type: ignore[type-arg]
    credential_store: Any,
    state_providers: Sequence[SyncedStatePort] = (),
    import_gates: Sequence[ImportGate] = (),
    post_import_hooks: Sequence[PostImportHook] = (),
) -> SyncWiring:
    cred_sync = CredentialSyncAdapter(db_path, master_key)
    home = str(pathlib.Path.home())

    def _bundle(root: pathlib.Path) -> BundlePort:
        return Bundle(root)

    service = SyncService(
        exporter=SyncExporter(
            resource_svc,
            cred_sync,
            state_providers=state_providers,
            home=home,
        ),
        importer=SyncImporter(
            resource_svc,
            cred_sync,
            state_providers=state_providers,
            import_gates=import_gates,
            post_import_hooks=post_import_hooks,
            home=home,
        ),
        credentials=cred_sync,
        master_key=master_key,
        audit=audit,
        bundle_factory=_bundle,
    )
    set_sync_service(service)

    def _mirror(worktree: pathlib.Path) -> GitMirrorPort:
        return GitMirror(worktree)

    backup = BackupService(
        remotes=SqlAlchemySyncRemoteRepo(sm),
        # The same ``SyncService``, not a second one: a backup run exports
        # through its lock, so a manual export cannot interleave with a run.
        sync=service,
        # A factory rather than one mirror, because the working tree is part of
        # the remote's config and the user can move it without a restart.
        mirror_factory=_mirror,
        credentials=CredentialResolver(credential_store),
        audit=audit,
    )
    set_backup_service(backup)
    return SyncWiring(sync=service, backup=backup)


def start_sync(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    db_path: pathlib.Path,
    master_key: MasterKeyManager,
    sm: async_sessionmaker,  # type: ignore[type-arg]
    credential_store: Any,
) -> BackupService:
    """Wire export/import and the backup service. Kind modules registered their
    shared-state providers, import gates and post-import hooks on ``app.state``
    during composition, before this runs.

    Returns the backup service so the caller can start a worker over it —
    wiring and starting stay separate, because a test wants the graph without
    a timer.
    """
    providers = tuple(getattr(app.state, "sync_state_providers", ()) or ())
    gates = tuple(getattr(app.state, "sync_import_gates", ()) or ())
    hooks = tuple(getattr(app.state, "sync_post_import_hooks", ()) or ())
    wiring = wire_sync(
        resource_svc,
        audit,
        db_path,
        master_key,
        sm,
        credential_store,
        state_providers=providers,
        import_gates=gates,
        post_import_hooks=hooks,
    )
    app.state.sync_service = wiring.sync
    app.state.backup_service = wiring.backup
    return wiring.backup


def start_backup_worker(app: FastAPI, backup: BackupService) -> BackupWorker:
    """Start the timer that backs the vault up, shaped like ``RetentionWorker``.

    No interval is passed: the worker re-reads the configured remote's interval
    on every tick, so a user who shortens it in the UI is believed without a
    daemon restart, and a vault with no remote configured ticks harmlessly on
    the default cadence until one appears.
    """
    worker = BackupWorker(backup)
    app.state.backup_worker = worker
    app.state.backup_worker_task = asyncio.create_task(worker.run())
    return worker


async def stop_backup_worker(app: FastAPI) -> None:
    """Best-effort teardown, mirroring the retention worker's: signal the loop,
    give it a moment to end a run cleanly, then cancel."""
    worker: BackupWorker | None = getattr(app.state, "backup_worker", None)
    if worker is not None:
        worker.stop()
    task: asyncio.Task[None] | None = getattr(app.state, "backup_worker_task", None)
    if task is None:
        return
    try:
        await asyncio.wait_for(task, timeout=2.0)
    except (TimeoutError, asyncio.CancelledError):
        task.cancel()
