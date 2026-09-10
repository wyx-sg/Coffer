"""Composition root for the vault export/import service
(spec vault-export-import, ADR: vault-export-import).

Builds the object graph (bundle IO factory, ciphertext credential adapter,
exporter/importer) over the same master-key manager the rest of the daemon
uses and registers the HTTP service singleton. Nothing here starts a
background task: export and import run only when the user asks.
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence

from fastapi import FastAPI

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.importer import SyncImporter
from coffer.application.sync.ports import BundlePort, ImportGate, PostImportHook, SyncedStatePort
from coffer.application.sync.service import SyncService
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.infrastructure.sync.bundle import Bundle
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter
from coffer.surfaces.http.sync_routes import set_sync_service


def wire_sync(
    resource_svc: ResourceService,
    audit: AuditService,
    db_path: pathlib.Path,
    master_key: MasterKeyManager,
    state_providers: Sequence[SyncedStatePort] = (),
    import_gates: Sequence[ImportGate] = (),
    post_import_hooks: Sequence[PostImportHook] = (),
) -> SyncService:
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
    return service


def start_sync(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    db_path: pathlib.Path,
    master_key: MasterKeyManager,
) -> None:
    """Wire export/import. Kind modules registered their shared-state
    providers, import gates and post-import hooks on ``app.state`` during
    composition, before this runs."""
    providers = tuple(getattr(app.state, "sync_state_providers", ()) or ())
    gates = tuple(getattr(app.state, "sync_import_gates", ()) or ())
    hooks = tuple(getattr(app.state, "sync_post_import_hooks", ()) or ())
    app.state.sync_service = wire_sync(
        resource_svc,
        audit,
        db_path,
        master_key,
        state_providers=providers,
        import_gates=gates,
        post_import_hooks=hooks,
    )
