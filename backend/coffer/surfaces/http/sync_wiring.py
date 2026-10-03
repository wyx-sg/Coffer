"""Composition root for sync (spec vault-sync; ADR
sync-applies-clean-merges-and-stops-on-any-conflict).

Builds the thin round over the process's one vault writer and hands it to the
service the surfaces call::

    vault writer (+ its validator, + the join's held paths)
        → VaultSyncGit, JsonRoundState, ConflictScratch, HostMachine
        → RoundDeps → RoundEngine
        → SyncService (remote file, runs.db history, push token through the
          secret boundary, master key, plugin inventory)
        → SyncWorker

The service's lock is the vault-write lock the curation pass takes too, so a
round never runs beside a pass (spec vault-sync "Never overlap a curation pass
and a round").
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import coffer
from coffer.application.audit_service import AuditService
from coffer.application.features import FeatureService
from coffer.application.platform_port import PlatformPort
from coffer.application.resource_service import ResourceService
from coffer.application.sync.inventory import AgentPluginInventory
from coffer.application.sync.round_deps import RoundDeps
from coffer.application.sync.round_engine import RoundEngine
from coffer.application.sync.service import SyncService
from coffer.application.sync.token import BoundaryToken
from coffer.application.sync.worker import SyncWorker
from coffer.domain.features import SYNC
from coffer.domain.secrets import SecretDestination, sync_remote_destination
from coffer.domain.vault.writes import Change, TreeReader, Validator, Verdict
from coffer.infrastructure.daemon.config import write_machine_name
from coffer.infrastructure.persistence.sync_runs_repo import SyncRunRepo
from coffer.infrastructure.platform.host import machine_label
from coffer.infrastructure.secret.encrypted_store import EncryptedSecretStore
from coffer.infrastructure.secret.master_key import MasterKeyManager
from coffer.infrastructure.secret.plaintext_scan import find_in_text
from coffer.infrastructure.sync.cloud_folder import synchroniser_of
from coffer.infrastructure.sync.identity import machine_name, resolve_identity
from coffer.infrastructure.sync.local_state import ConflictScratch, JsonRemoteStore, JsonRoundState
from coffer.infrastructure.sync.machine_descriptor import HostMachine
from coffer.infrastructure.sync.master_key import ResolvedMasterKey, SecretFiles
from coffer.infrastructure.sync.vault_git import VaultSyncGit
from coffer.infrastructure.sync.vault_move import VaultMover
from coffer.infrastructure.vault.git import git_available
from coffer.infrastructure.vault.home import vault_root
from coffer.infrastructure.vault.instance import vault_writer
from coffer.infrastructure.vault.writer import VaultWriter
from coffer.surfaces.http.knowledge.curation_state import set_curation_hold, set_vault_write_lock
from coffer.surfaces.http.secret_boundary_wiring import boundary_resolver
from coffer.surfaces.http.sync_dependencies import set_sync_service

_log = logging.getLogger(__name__)


class SyncWiring(NamedTuple):
    """The service the surfaces call; the curation worker reads its lock,
    this machine's id and whether a round waits for a person."""

    service: SyncService


def _validator_of(writer: VaultWriter) -> Validator:
    """The writer's own validator, read at each call: a merged tree meets the
    same checks a person's edit and a daemon write meet (spec vault-storage
    "Admit every vault write through one compare-and-swap path")."""

    def validate(changes: Sequence[Change], history: TreeReader) -> Verdict:
        return writer.validator(changes, history)

    return validate


def _plugins() -> Any:
    """The agent plugin service, once the agent kind has published it."""
    from coffer.surfaces.http.workspace_dependencies import get_agent_plugin_service

    try:
        return get_agent_plugin_service()
    except RuntimeError:
        return None


async def _reconcile_imported() -> None:
    """One reconcile pass with the import's warrant, after a round applied
    another machine's changes here."""
    from coffer.domain.reconcile import Trigger
    from coffer.surfaces.http.reconcile_dependencies import get_reconciler

    await get_reconciler().run(trigger=Trigger.IMPORT)


def _reconciler_hold() -> contextlib.AbstractAsyncContextManager[object]:
    """Keep the reconciler's passes out while a round, its import pass and
    its history are written (spec resource-framework "Converge what Coffer
    writes outside its database with one reconciler")."""
    from coffer.surfaces.http.reconcile_dependencies import get_reconciler

    return get_reconciler().hold()


def wire_sync(
    *,
    resources: ResourceService,
    audit: AuditService,
    sm: async_sessionmaker[AsyncSession],
    master_key: MasterKeyManager,
    secret_store: EncryptedSecretStore,
    platform: PlatformPort,
) -> SyncWiring:
    identity = resolve_identity()
    # The running secret store is told an imported key, so a secret saved
    # after the import is sealed under it.
    key = ResolvedMasterKey(master_key, on_install=secret_store.use_key)
    writer = vault_writer()
    state = JsonRoundState()
    # A join's differing files stay as they are here, never settled, until
    # the person chooses (spec vault-sync "Join a new machine by taking the union").
    writer.set_held(lambda: {c.path for c in state.join_choices()})
    machine = HostMachine(
        machine_id=identity.machine_id,
        name=machine_name,
        os_label=platform.os_label,
        coffer_version=coffer.__version__,
        key_fingerprint=key.fingerprint,
    )
    git = VaultSyncGit(writer.repo)
    deps = RoundDeps(
        git=git,
        state=state,
        writer=writer,
        machine=machine,
        scratch=ConflictScratch(),
        validate=_validator_of(writer),
        cloud_folder=lambda: synchroniser_of(vault_root(), home=Path.home()),
        find_plaintext=find_in_text,
    )
    service = SyncService(
        engine=RoundEngine(deps),
        remotes=JsonRemoteStore(),
        history=SyncRunRepo(sm),
        token=BoundaryToken(boundary_resolver(secret_store)),
        machine=machine,
        master_key=key,
        secrets=SecretFiles(key),
        probe=git,
        audit=audit,
        set_machine_name=write_machine_name,
        vault_path=vault_root,
        mover=VaultMover(),
        inventory=AgentPluginInventory(resources, _plugins),
        after_apply=_reconcile_imported,
        hold=_reconciler_hold,
        git_available=git_available,
        host_label=machine_label,
    )
    return SyncWiring(service=service)


def start_sync(
    *,
    resources: ResourceService,
    audit: AuditService,
    sm: async_sessionmaker[AsyncSession],
    master_key: MasterKeyManager,
    secret_store: EncryptedSecretStore,
    platform: PlatformPort,
) -> SyncWiring:
    """Wire sync and publish it: the routes' service, and the vault-write lock
    the curation pass takes (timer and button alike)."""
    wiring = wire_sync(
        resources=resources,
        audit=audit,
        sm=sm,
        master_key=master_key,
        secret_store=secret_store,
        platform=platform,
    )
    set_sync_service(wiring.service)
    set_vault_write_lock(wiring.service.lock)
    set_curation_hold(wiring.service.divergence_outstanding)
    return wiring


def start_sync_worker(wiring: SyncWiring, features: FeatureService) -> SyncWorker:
    """Rounds on the remote's interval; the first 30 s after start. Nothing
    runs while the ``sync`` feature is off."""
    worker = SyncWorker(wiring.service, is_enabled=lambda: features.is_enabled(SYNC))
    worker.start()
    return worker


async def stop_sync_worker(worker: SyncWorker) -> None:
    """Best-effort teardown: a round that does not yield within the grace
    period is abandoned, and said so."""
    try:
        await asyncio.wait_for(worker.stop(), timeout=2.0)
    except TimeoutError:
        _log.warning("sync.worker.stop_timed_out", extra={"timeout_s": 2.0})
    except asyncio.CancelledError:
        _log.debug("sync.worker.stop_cancelled")


def sync_remote_secret_source() -> Callable[
    [], Awaitable[list[tuple[SecretDestination, Mapping[str, str], str]]]
]:
    """Where the push token goes right now, for the secret boundary's listing
    (spec vault-sync "Hold a push token pointed at a new URL until approved")."""

    async def current() -> list[tuple[SecretDestination, Mapping[str, str], str]]:
        remote = await asyncio.to_thread(JsonRemoteStore().get)
        if remote is None or not remote.secret_ref:
            return []
        return [(sync_remote_destination(remote.url), {"token": remote.secret_ref}, "user")]

    return current


__all__ = [
    "SyncWiring",
    "start_sync",
    "start_sync_worker",
    "stop_sync_worker",
    "sync_remote_secret_source",
    "wire_sync",
]
