"""Start the daemon's background workers, in one place.

Four timers that outlive a request: retention pruning, the vault converge
round, the knowledge curation pass, and the memory distil pass. They are gathered
here rather than inlined in the lifespan because each needs a different slice
of the graph, and reading which worker gets what is the only reason to look at
this code at all.

Order matters once: sync is wired before the curation worker starts, because
that worker takes the converge round's lock, this machine's identity and the
pending-round state from the sync graph — as parameters, not by looking them up
later. Nothing in ``start_sync`` depends on curation.
"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from coffer.application.agent.transcript_warm_worker import TranscriptWarmWorker
from coffer.application.audit_service import AuditService
from coffer.application.engine.resolve import InternalEngineConnection
from coffer.application.internal_engine_config_service import InternalEngineConfigService
from coffer.application.knowledge.curate import CurationPass
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.knowledge.skill_delivery import KnowledgeSkillDelivery
from coffer.application.memory.service import MemoryService
from coffer.application.resource_service import ResourceService
from coffer.application.retention_service import RetentionService
from coffer.application.retention_worker import RetentionWorker
from coffer.application.sync.worker import ConvergeWorker
from coffer.infrastructure.agent.transcript_reader import FileTranscriptReader
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.infrastructure.logging.files import prune_log_dir
from coffer.surfaces.http.curation_wiring import start_curation_worker
from coffer.surfaces.http.memory.distil_state import DistilRunner
from coffer.surfaces.http.memory_wiring import start_aggregate_worker, start_distil_worker
from coffer.surfaces.http.sync_contributions import SyncContributions
from coffer.surfaces.http.sync_wiring import SyncWiring, start_converge_worker, start_sync
from coffer.surfaces.http.transcript_warm_wiring import start_transcript_warm_worker


@dataclass(frozen=True)
class BackgroundWorkers:
    """Every long-lived worker the lifespan must stop, plus the sync graph
    (returned so the lifespan can see what the curation worker was given)."""

    retention_worker: RetentionWorker
    retention_task: asyncio.Task[None]
    sync: SyncWiring
    converge_worker: ConvergeWorker
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
    skill_delivery: KnowledgeSkillDelivery,
    distil: DistilRunner,
    memory_service: MemoryService,
    transcript_reader: FileTranscriptReader,
    resource_svc: ResourceService,
    audit: AuditService,
    engine_config: InternalEngineConfigService,
    internal_connection: InternalEngineConnection,
    credential_resolver: Callable[[str], str],
    db_path: pathlib.Path,
    sm: async_sessionmaker[AsyncSession],
    credential_store: EncryptedCredentialStore,
    master_key: MasterKeyManager,
    sync_contributions: SyncContributions,
) -> BackgroundWorkers:
    retention_worker = RetentionWorker(retention_svc, prune_logs=prune_log_dir)
    retention_task = asyncio.create_task(retention_worker.run())

    # Vault sync (spec vault-sync): a converge round on a timer beside the
    # retention worker, re-reading its interval from the configured remote. It
    # is a no-op until the user configures one. Wired FIRST among the vault
    # rewriters: the curation worker below takes its lock and state.
    sync = start_sync(
        resource_svc,
        audit,
        db_path,
        master_key,
        sm,
        credential_store,
        sync_contributions,
        # The conflict resolver rides the same internal connection every other
        # internal-LLM consumer uses — Coffer's own engine, not the provider
        # kind's service, is what answers for it.
        models=internal_connection,
        credential_resolver=credential_resolver,
    )
    converge_worker = start_converge_worker(sync, sm)

    # Curation: a sweep that folds whatever sources have changed since they
    # were last consumed into the collection's topic documents.
    curation_task = start_curation_worker(
        knowledge_service, curation_pass, skill_delivery, resource_svc, engine_config, sync
    )
    distil_task = start_distil_worker(distil, resource_svc, engine_config)
    # Aggregation (spec memory FR-007): a catch-up pass now, then hourly. It
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
        converge_worker=converge_worker,
        curation_task=curation_task,
        distil_task=distil_task,
        aggregate_task=aggregate_task,
        warm_worker=warm_worker,
        warm_task=warm_task,
    )
