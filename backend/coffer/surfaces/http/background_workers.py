"""Start the daemon's background workers, in one place.

Six timers that outlive a request: retention pruning, the vault sync
round, the knowledge curation pass, the memory distil pass, the memory
aggregate pass, and the transcript summary cache warm-up. They are gathered
here rather than inlined in the lifespan because each needs a different slice
of the graph, and reading which worker gets what is the only reason to look at
this code at all.

Order matters once: sync is wired before the curation worker starts, because
that worker takes the sync round's lock, this machine's identity and whether a
round waits for a person from the sync graph — as parameters, not by looking
them up later. Nothing in ``start_sync`` depends on curation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.application.agent.transcript_warm_worker import TranscriptWarmWorker
from coffer.application.audit_service import AuditService
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.application.knowledge.curate import CurationPass
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.memory.service import MemoryService
from coffer.application.platform_port import PlatformPort
from coffer.application.resource_service import ResourceService
from coffer.application.retention_service import RetentionService
from coffer.application.retention_worker import RetentionWorker
from coffer.application.sync.worker import SyncWorker
from coffer.infrastructure.agent.transcript_reader import FileTranscriptReader
from coffer.infrastructure.logging.files import prune_log_dir
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore
from coffer.infrastructure.secret.master_key import MasterKeyManager
from coffer.surfaces.http.curation_wiring import start_curation_worker
from coffer.surfaces.http.guide_wiring import BuiltinGuide
from coffer.surfaces.http.memory.distil_state import DistilRunner
from coffer.surfaces.http.memory_wiring import start_aggregate_worker, start_distil_worker
from coffer.surfaces.http.sync_wiring import SyncWiring, start_sync, start_sync_worker
from coffer.surfaces.http.transcript_warm_wiring import start_transcript_warm_worker


@dataclass(frozen=True)
class BackgroundWorkers:
    """Every long-lived worker the lifespan must stop, plus the sync graph
    (returned so the lifespan can see what the curation worker was given)."""

    retention_worker: RetentionWorker
    retention_task: asyncio.Task[None]
    sync: SyncWiring
    sync_worker: SyncWorker
    curation_task: asyncio.Task[None]
    distil_task: asyncio.Task[None]
    aggregate_task: asyncio.Task[None]
    warm_worker: TranscriptWarmWorker
    warm_task: asyncio.Task[None]


def start_background_workers(
    *,
    retention_svc: RetentionService,
    knowledge_service: KnowledgeService,
    curation_pass: CurationPass,
    guide: BuiltinGuide,
    distil: DistilRunner,
    memory_service: MemoryService,
    transcript_reader: FileTranscriptReader,
    resource_svc: ResourceService,
    audit: AuditService,
    engine_config: InternalEngineConfigService,
    sm: async_sessionmaker[AsyncSession],
    secret_store: EncryptedSecretStore,
    master_key: MasterKeyManager,
    platform: PlatformPort,
) -> BackgroundWorkers:
    retention_worker = RetentionWorker(retention_svc, prune_logs=prune_log_dir)
    retention_task = asyncio.create_task(retention_worker.run())

    # Vault sync (spec vault-sync): a round on the configured remote's
    # interval, nothing until one is configured. Wired FIRST among the vault
    # rewriters: the curation worker below takes its lock and state.
    sync = start_sync(
        resources=resource_svc,
        audit=audit,
        sm=sm,
        master_key=master_key,
        secret_store=secret_store,
        platform=platform,
    )
    sync_worker = start_sync_worker(sync)

    # Curation: a sweep that merges each collection's inbox into its
    # documents, then carries through any document edited since it was last
    # curated.
    curation_task = start_curation_worker(
        knowledge_service, curation_pass, guide, resource_svc, engine_config, sync
    )
    distil_task = start_distil_worker(distil, resource_svc, engine_config)
    # Aggregation (spec memory "Aggregate on an interval and on demand"): a
    # catch-up pass now, then hourly. It
    # only reads the agents' own memory and only writes the derived tree, so
    # nothing here has to wait on the vault rewriters above.
    aggregate_task = start_aggregate_worker(memory_service, engine_config)
    # The transcript summary cache's warm pass, so the first visit to an
    # agent's Conversations tab is never the one that pays the cold read.
    warm_worker, warm_task = start_transcript_warm_worker(transcript_reader, resource_svc)

    return BackgroundWorkers(
        retention_worker=retention_worker,
        retention_task=retention_task,
        sync=sync,
        sync_worker=sync_worker,
        curation_task=curation_task,
        distil_task=distil_task,
        aggregate_task=aggregate_task,
        warm_worker=warm_worker,
        warm_task=warm_task,
    )
