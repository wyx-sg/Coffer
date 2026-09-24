"""Composition root for vault convergence (spec vault-sync, ADR vault-sync).

Builds the whole object graph one round needs, in the order the dependencies
run::

    machine identity → MachineRegistry
                     → Bundle (held paths fed from convergence state)
                     → appliers → ConflictArbiter → JoinResolver
                     → round_factory → ConvergeService → ConvergeWorker

Everything that depends on **which** working tree is in play is built inside
``round_factory`` rather than here, because the working tree is part of the
remote's configuration and the user can move it without restarting the daemon.
That is the same reason ``ConvergeService`` takes a mirror *factory*.

The one subtlety worth stating: the ``serialize`` callable a round is given
does two things as one step — it exports the vault into the tree and writes
this machine's descriptor. They belong together because the descriptor names
the commit this machine has absorbed, and a descriptor published in a different
commit from the state it describes is how a returning machine recovers the
wrong base.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import pathlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import coffer
from coffer.application.audit_service import AuditService
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.resource_service import ResourceService
from coffer.application.sync.appliers import (
    CredentialApplier,
    StateApplier,
    TreeApplier,
)
from coffer.application.sync.appliers_resource import ResourceApplier
from coffer.application.sync.conflicts import ConflictArbiter
from coffer.application.sync.convergence import ConvergeRound
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.joining import JoinResolver
from coffer.application.sync.machines import MachineRegistry
from coffer.application.sync.ports import (
    GitMirrorPort,
    ImportGate,
    ImportNormaliser,
    PostImportHook,
    SyncedStatePort,
)
from coffer.application.sync.service import ConvergeService
from coffer.application.sync.worker import ConvergeWorker
from coffer.domain.sync.backup import DEFAULT_WORKTREE
from coffer.domain.sync.diff import DeletionGuard
from coffer.domain.sync.models import ExportSummary
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.infrastructure.daemon.config import write_machine_name
from coffer.infrastructure.llm.llm_completion import LangchainLlmCompletion
from coffer.infrastructure.memory.paths import memory_root
from coffer.infrastructure.persistence.convergence_state_repo import SqlAlchemyConvergenceStateRepo
from coffer.infrastructure.persistence.sync_remote_repo import SqlAlchemySyncRemoteRepo
from coffer.infrastructure.sync.bundle import Bundle
from coffer.infrastructure.sync.conflict_resolver import (
    AgenticConflictResolver,
    InternalModelPort,
)
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter, ResolvedMasterKey
from coffer.infrastructure.sync.git_mirror import GitMirror
from coffer.infrastructure.sync.identity import coffer_dir, machine_name, resolve_identity
from coffer.infrastructure.sync.paths import (
    knowledge_root,
    non_converging_tree_paths,
    skills_root,
)
from coffer.surfaces.http.knowledge.curation_state import set_vault_write_lock
from coffer.surfaces.http.sync_contributions import SyncContributions
from coffer.surfaces.http.sync_routes import set_machine_registry, set_sync_service

_log = logging.getLogger(__name__)


class SyncWiring(NamedTuple):
    """What the composition root hands back: the service the surfaces call
    (and the curation worker asks whether a divergence is outstanding), the
    registry the machines table reads, and the convergence state."""

    service: ConvergeService
    registry: MachineRegistry
    state: SqlAlchemyConvergenceStateRepo


def _key_fingerprint(master_key: ResolvedMasterKey) -> str | None:
    """The short hash that rides in this machine's descriptor, never the key.

    Read once at wiring: a key imported later reaches the descriptor at the
    next daemon start, which is when the credentials it unlocks become usable
    anyway.
    """
    key = master_key.export_key()
    return hashlib.sha256(key).hexdigest()[:12] if key else None


def wire_sync(
    resource_svc: ResourceService,
    audit: AuditService,
    db_path: pathlib.Path,
    master_key: MasterKeyManager,
    sm: async_sessionmaker[AsyncSession],
    credential_store: EncryptedCredentialStore,
    *,
    models: InternalModelPort,
    credential_resolver: Callable[[str], str],
    state_providers: Sequence[SyncedStatePort] = (),
    import_gates: Sequence[ImportGate] = (),
    import_normalisers: Sequence[ImportNormaliser] = (),
    post_import_hooks: Sequence[PostImportHook] = (),
) -> SyncWiring:
    # Resolved once and shared — the fingerprint, every round's locked-ref check
    # and the key export/import all read this one — so a key kept in the
    # keychain costs one prompt per daemon start, not one per round.
    resolved_key = ResolvedMasterKey(master_key)
    cred_sync = CredentialSyncAdapter(db_path, resolved_key)
    home = str(pathlib.Path.home())
    remotes = SqlAlchemySyncRemoteRepo(sm)
    state = SqlAlchemyConvergenceStateRepo(sm)
    providers = list(state_providers)
    gates = list(import_gates)
    normalisers = list(import_normalisers)
    hooks = list(post_import_hooks)

    identity = resolve_identity()
    registry = MachineRegistry(
        machine_id=identity.machine_id,
        machine_name=machine_name(),
        derived=identity.derived,
        coffer_version=coffer.__version__,
        resources=resource_svc,
        key_fingerprint=_key_fingerprint(resolved_key),
    )
    exporter = SyncExporter(resource_svc, cred_sync, state_providers=providers, home=home)

    async def _serialize(worktree: pathlib.Path) -> ExportSummary:
        """Step 1 of a round: the vault, and this machine's row, into the tree.

        The held paths are read once here and handed to the bundle as a view
        that resolves at write time. They are what stops a document this vault
        failed to absorb from being published as a deletion — the retry set's
        whole purpose (spec vault-sync "Never export a retry-set path as a deletion").
        """
        retry, not_applicable = await state.held_paths()
        held = retry | not_applicable
        bundle = Bundle(worktree, held_paths=lambda: held)
        remote = await remotes.get()
        summary = await exporter.export(
            bundle, with_credentials=bool(remote and remote.include_credentials)
        )
        # The empty tree is the base a machine joining as new diffs against,
        # not a commit it absorbed. Publishing it as ``last_converged_commit``
        # would hand a returning machine a base git cannot resolve, and the
        # join would be refused as unrecoverable rather than recovered.
        pointer = await state.pointer()
        commit = pointer if pointer and pointer != GitMirror.EMPTY_TREE else None
        await registry.publish_self(bundle, commit=commit, today=datetime.now(tz=UTC).date())
        return summary

    def _round(mirror: GitMirrorPort, branch: str) -> ConvergeRound:
        worktree = _worktree_of(mirror)
        resolver = AgenticConflictResolver(
            worktree=worktree,
            completion=LangchainLlmCompletion(),
            models=models,
            credential_resolver=credential_resolver,
        )
        return ConvergeRound(
            mirror=mirror,
            state=state,
            appliers=[
                TreeApplier("knowledge/", worktree=worktree, live_root=knowledge_root()),
                # The skills tree carries one folder this machine generates for
                # itself and therefore never receives from another (spec
                # vault-sync "Withhold derived output in both halves"). ``Bundle``
                # defaults to the same set on
                # the publish side; the applier is handed it explicitly because
                # the application layer may not read infrastructure.
                TreeApplier(
                    "skills/",
                    worktree=worktree,
                    live_root=skills_root(),
                    excluded=non_converging_tree_paths(),
                ),
                ResourceApplier(
                    resource_svc,
                    worktree=worktree,
                    gates=gates,
                    normalisers=normalisers,
                    home=home,
                ),
                StateApplier(providers, worktree=worktree, home=home),
                CredentialApplier(cred_sync, worktree=worktree),
            ],
            arbiter=ConflictArbiter(resolver),
            joining=JoinResolver(machine_id=identity.machine_id, branch=branch),
            serialize=lambda: _serialize(worktree),
            guard=DeletionGuard(),
            branch=branch,
            # Asked after the apply which refs it now holds without a key.
            credentials=cred_sync,
            # A kind owns more than its row: a native config file, a shim, a
            # delivered skill. The applier writes the row; these put this
            # machine's side of it back in step (spec vault-sync
            # "Re-run post-import hooks after applying").
            post_import=hooks,
        )

    service = ConvergeService(
        remotes=remotes,
        state=state,
        round_factory=_round,
        # A factory rather than one mirror, because the working tree is part of
        # the remote's config and the user can move it without a restart.
        mirror_factory=lambda worktree: GitMirror(worktree),
        # The machines page reads the registry straight out of the working
        # tree, so it needs a bundle over it without running a round.
        bundle_factory=lambda worktree: Bundle(worktree),
        set_machine_name=write_machine_name,
        credentials=CredentialResolver(credential_store),
        credential_store=cred_sync,
        master_key=resolved_key,
        audit=audit,
        # A working tree may not sit at, inside or above any of these: the
        # round mirrors the first three *into* the tree and ``reset --hard``s
        # it, and the last holds the database and the master key.
        protected_roots=[knowledge_root(), skills_root(), memory_root()],
        coffer_dir=coffer_dir(),
    )
    return SyncWiring(service=service, registry=registry, state=state)


def _worktree_of(mirror: GitMirrorPort) -> pathlib.Path:
    """Where the round's appliers read the merged documents from.

    The port deliberately exposes no path — it is an interface over git
    operations, not over a directory — so the composition root, which knows it
    injected a :class:`GitMirror`, is the right place to recover one. A mirror
    from anywhere else falls back to the configured default rather than
    guessing.
    """
    if isinstance(mirror, GitMirror):
        return mirror.worktree
    return pathlib.Path(DEFAULT_WORKTREE).expanduser()


def start_sync(
    resource_svc: ResourceService,
    audit: AuditService,
    db_path: pathlib.Path,
    master_key: MasterKeyManager,
    sm: async_sessionmaker[AsyncSession],
    credential_store: EncryptedCredentialStore,
    contributions: SyncContributions,
    *,
    models: InternalModelPort,
    credential_resolver: Callable[[str], str],
) -> SyncWiring:
    """Wire convergence over what the kinds contributed during composition
    (their shared-state providers, import gates and normalisers, and post-import
    hooks).

    Returns the graph so the caller can start a worker over it — wiring and
    starting stay separate, because a test wants the graph without a timer.
    """
    wiring = wire_sync(
        resource_svc,
        audit,
        db_path,
        master_key,
        sm,
        credential_store,
        models=models,
        credential_resolver=credential_resolver,
        state_providers=tuple(contributions.state_providers),
        import_gates=tuple(contributions.import_gates),
        import_normalisers=tuple(contributions.import_normalisers),
        post_import_hooks=tuple(contributions.post_import_hooks),
    )
    # The routes hold module-level singletons, matching every other surface
    # in this package.
    set_sync_service(wiring.service)
    # The tidy pass — timer and button alike — takes the round's own lock.
    set_vault_write_lock(wiring.service.lock)
    set_machine_registry(wiring.registry)
    return wiring


def start_converge_worker(
    wiring: SyncWiring, sm: async_sessionmaker[AsyncSession]
) -> ConvergeWorker:
    """Start the timer that converges the vault, shaped like ``RetentionWorker``.

    No interval is passed: the worker re-reads the configured remote's interval
    on every tick, so a user who shortens it in the UI is believed without a
    daemon restart, and a vault with no remote configured ticks harmlessly on
    the default cadence until one appears.
    """
    worker = ConvergeWorker(wiring.service, SqlAlchemySyncRemoteRepo(sm))
    worker.start()
    return worker


async def stop_converge_worker(worker: ConvergeWorker) -> None:
    """Best-effort teardown, mirroring the retention worker's: a round that
    does not yield within the grace period is abandoned, and said so."""
    try:
        await asyncio.wait_for(worker.stop(), timeout=2.0)
    except TimeoutError:
        _log.warning("sync.converge_worker.stop_timed_out", extra={"timeout_s": 2.0})
    except asyncio.CancelledError:
        _log.debug("sync.converge_worker.stop_cancelled")
