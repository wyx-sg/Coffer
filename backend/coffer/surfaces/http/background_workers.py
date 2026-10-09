"""Start the daemon's background workers, in one place.

Four timers that outlive a request: retention pruning, the vault sync
round, the knowledge sweep and the memory sync. They are gathered
here rather than inlined in the lifespan because each needs a different slice
of the graph, and reading which worker gets what is the only reason to look at
this code at all.

"""

from __future__ import annotations

import asyncio
import pathlib
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.application.audit_service import AuditService
from coffer.application.features import FeatureService
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.platform_port import PlatformPort
from coffer.application.resource_service import ResourceService
from coffer.application.retention_service import RetentionService
from coffer.application.retention_worker import RetentionWorker
from coffer.application.runtime.supervisor import spawn_restarting
from coffer.application.sync.worker import SyncWorker
from coffer.infrastructure.logging.files import prune_log_dir
from coffer.infrastructure.persistence.space import reclaim_free_pages
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore
from coffer.infrastructure.secret.master_key import MasterKeyManager
from coffer.surfaces.http.guide_wiring import BuiltinGuide
from coffer.surfaces.http.knowledge_sweep_wiring import start_knowledge_sweep
from coffer.surfaces.http.memory_sync_wiring import start_memory_sync_worker, wire_memory_sync
from coffer.surfaces.http.sync_wiring import SyncWiring, start_sync, start_sync_worker


@dataclass(frozen=True)
class BackgroundWorkers:
    """Every long-lived worker the lifespan must stop, plus the sync graph."""

    retention_worker: RetentionWorker
    retention_task: asyncio.Task[None]
    sync: SyncWiring
    sync_worker: SyncWorker
    knowledge_sweep_task: asyncio.Task[None]
    memory_sync_task: asyncio.Task[None]


def start_background_workers(
    *,
    retention_svc: RetentionService,
    knowledge_service: KnowledgeService,
    guide: BuiltinGuide,
    resource_svc: ResourceService,
    audit: AuditService,
    engine_config: InternalEngineConfigService,
    sm: async_sessionmaker[AsyncSession],
    secret_store: EncryptedSecretStore,
    master_key: MasterKeyManager,
    features: FeatureService,
    platform: PlatformPort,
    history_db: pathlib.Path | None,
) -> BackgroundWorkers:
    retention_worker = RetentionWorker(
        retention_svc,
        prune_logs=prune_log_dir,
        reclaim_space=lambda: reclaim_free_pages(history_db),
    )
    retention_task = spawn_restarting(retention_worker.run, name="retention-worker")

    # Vault sync (spec vault-sync): a round on the configured remote's
    # interval, nothing until one is configured.
    sync = start_sync(
        resources=resource_svc,
        audit=audit,
        sm=sm,
        master_key=master_key,
        secret_store=secret_store,
        platform=platform,
    )
    sync_worker = start_sync_worker(sync)

    # Every experimental feature's pass reads its switch at the top of each
    # round and skips it while off (spec experimental-features).
    # The knowledge sweep: refresh the guide, promote what landed in a
    # collection's inbox, and commit edits found on disk.
    knowledge_sweep_task = start_knowledge_sweep(knowledge_service, guide, resource_svc, features)
    # The memory sync into each agent's own memory (spec memory "Sync on an
    # interval and on demand"): a sync at start, then on its interval.
    memory_sync = wire_memory_sync(resource_svc, audit, engine_config)
    memory_sync_task = start_memory_sync_worker(memory_sync, engine_config, features)

    return BackgroundWorkers(
        retention_worker=retention_worker,
        retention_task=retention_task,
        sync=sync,
        sync_worker=sync_worker,
        knowledge_sweep_task=knowledge_sweep_task,
        memory_sync_task=memory_sync_task,
    )
