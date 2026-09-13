"""Start the daemon's background workers, in one place.

Four timers that outlive a request: retention pruning, the knowledge tidy pass,
the memory organise pass, and the vault converge round. They are gathered here
rather than inlined in the lifespan because each needs a different slice of the
graph, and reading which worker gets what is the only reason to look at this
code at all.

Order matters once: sync is wired before its worker starts, and the tidy worker
is started before sync only in the sense that it reads ``app.state`` lazily —
it takes the converge round's lock through ``app.state.sync_service``, which
``start_sync`` has published by the time a tick actually runs.
"""

from __future__ import annotations

import asyncio
import pathlib
from typing import Any

from fastapi import FastAPI

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.resource_service import ResourceService
from coffer.application.retention_service import RetentionService
from coffer.application.retention_worker import RetentionWorker
from coffer.infrastructure.logging.files import prune_log_dir
from coffer.surfaces.http.credential_composition import get_master_key_manager
from coffer.surfaces.http.memory_wiring import start_organise_worker
from coffer.surfaces.http.sync_wiring import start_converge_worker, start_sync
from coffer.surfaces.http.tidy_wiring import start_tidy_worker


def start_background_workers(
    app: FastAPI,
    *,
    retention_svc: RetentionService,
    knowledge_service: KnowledgeService,
    resource_svc: ResourceService,
    audit: AuditService,
    db_path: pathlib.Path,
    sm: Any,
    credential_store: Any,
) -> None:
    worker = RetentionWorker(retention_svc, prune_logs=prune_log_dir)
    app.state.retention_worker = worker
    app.state.retention_worker_task = asyncio.create_task(worker.run())

    # The notes tidy pass: on idle after a write, and on a periodic sweep.
    start_tidy_worker(app, knowledge_service)
    start_organise_worker(app, resource_svc)

    # Vault sync (spec vault-sync): a converge round on a timer beside the
    # retention worker, re-reading its interval from the configured remote. It
    # is a no-op until the user configures one.
    start_converge_worker(
        app,
        start_sync(
            app, resource_svc, audit, db_path, get_master_key_manager(), sm, credential_store
        ),
        sm,
    )
