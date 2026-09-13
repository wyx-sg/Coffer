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
import contextlib
import hashlib
import pathlib
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, NamedTuple

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker

import coffer
from coffer.application.audit_service import AuditService
from coffer.application.credentials.resolver import CredentialResolver
from coffer.application.resource_service import ResourceService
from coffer.application.sync.appliers import (
    CredentialApplier,
    ResourceApplier,
    StateApplier,
    TreeApplier,
)
from coffer.application.sync.conflicts import ConflictArbiter
from coffer.application.sync.convergence import ConvergeRound
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.joining import JoinResolver
from coffer.application.sync.machines import MachineRegistry
from coffer.application.sync.ports import (
    GitMirrorPort,
    ImportGate,
    PostImportHook,
    SyncedStatePort,
)
from coffer.application.sync.service import ConvergeService
from coffer.application.sync.worker import ConvergeWorker
from coffer.domain.sync.backup import DEFAULT_WORKTREE
from coffer.domain.sync.diff import DeletionGuard
from coffer.domain.sync.models import ExportSummary
from coffer.infrastructure.credentials.master_key import MasterKeyManager
from coffer.infrastructure.daemon.config import write_machine_name
from coffer.infrastructure.llm.llm_completion import LangchainLlmCompletion
from coffer.infrastructure.persistence.convergence_state_repo import SqlAlchemyConvergenceStateRepo
from coffer.infrastructure.persistence.sync_remote_repo import SqlAlchemySyncRemoteRepo
from coffer.infrastructure.sync.bundle import Bundle
from coffer.infrastructure.sync.conflict_resolver import AgenticConflictResolver
from coffer.infrastructure.sync.credentials import CredentialSyncAdapter
from coffer.infrastructure.sync.git_mirror import GitMirror
from coffer.infrastructure.sync.identity import machine_name, resolve_identity
from coffer.infrastructure.sync.paths import knowledge_root, skills_root
from coffer.surfaces.http.knowledge.tidy_state import set_vault_write_lock
from coffer.surfaces.http.sync_routes import set_machine_registry, set_sync_service


class SyncWiring(NamedTuple):
    """What the composition root hands back: the service the surfaces call,
    the registry the machines table reads, and the convergence state the tidy
    worker consults before it rewrites anything."""

    service: ConvergeService
    registry: MachineRegistry
    state: SqlAlchemyConvergenceStateRepo


def _key_fingerprint(master_key: MasterKeyManager) -> str | None:
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
    sm: async_sessionmaker,  # type: ignore[type-arg]
    credential_store: Any,
    *,
    state_providers: Sequence[SyncedStatePort] = (),
    import_gates: Sequence[ImportGate] = (),
    post_import_hooks: Sequence[PostImportHook] = (),
    models: Any = None,
    credential_resolver: Any = None,
) -> SyncWiring:
    cred_sync = CredentialSyncAdapter(db_path, master_key)
    home = str(pathlib.Path.home())
    remotes = SqlAlchemySyncRemoteRepo(sm)
    state = SqlAlchemyConvergenceStateRepo(sm)
    providers = list(state_providers)
    gates = list(import_gates)
    hooks = list(post_import_hooks)

    identity = resolve_identity()
    registry = MachineRegistry(
        machine_id=identity.machine_id,
        machine_name=machine_name(),
        derived=identity.derived,
        coffer_version=coffer.__version__,
        resources=resource_svc,
        key_fingerprint=_key_fingerprint(master_key),
    )
    exporter = SyncExporter(resource_svc, cred_sync, state_providers=providers, home=home)

    async def _serialize(worktree: pathlib.Path) -> ExportSummary:
        """Step 1 of a round: the vault, and this machine's row, into the tree.

        The held paths are read once here and handed to the bundle as a view
        that resolves at write time. They are what stops a document this vault
        failed to absorb from being published as a deletion — the retry set's
        whole purpose (spec vault-sync "Why deletion is safe").
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
                TreeApplier("skills/", worktree=worktree, live_root=skills_root()),
                ResourceApplier(resource_svc, worktree=worktree, gates=gates, home=home),
                StateApplier(providers, worktree=worktree),
                CredentialApplier(cred_sync, worktree=worktree),
            ],
            arbiter=ConflictArbiter(resolver),
            joining=JoinResolver(machine_id=identity.machine_id, branch=branch),
            serialize=lambda: _serialize(worktree),
            guard=DeletionGuard(),
            branch=branch,
            # A kind owns more than its row: a native config file, a shim, a
            # delivered skill. The applier writes the row; these put this
            # machine's side of it back in step (spec vault-sync
            # ``## Applying a diff``).
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
        master_key=master_key,
        audit=audit,
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
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    db_path: pathlib.Path,
    master_key: MasterKeyManager,
    sm: async_sessionmaker,  # type: ignore[type-arg]
    credential_store: Any,
    models: Any = None,
    credential_resolver: Any = None,
) -> SyncWiring:
    """Wire convergence. Kind modules registered their shared-state providers
    and import gates on ``app.state`` during composition, before this runs.

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
        state_providers=tuple(getattr(app.state, "sync_state_providers", ()) or ()),
        import_gates=tuple(getattr(app.state, "sync_import_gates", ()) or ()),
        post_import_hooks=tuple(getattr(app.state, "sync_post_import_hooks", ()) or ()),
        models=models,
        credential_resolver=credential_resolver,
    )
    app.state.sync_service = wiring.service
    app.state.machine_registry = wiring.registry
    app.state.convergence_state = wiring.state
    # The routes hold module-level singletons rather than reaching into
    # app.state, matching every other surface in this package.
    set_sync_service(wiring.service)
    # The tidy pass — timer and button alike — takes the round's own lock.
    set_vault_write_lock(wiring.service.lock)
    set_machine_registry(wiring.registry)
    return wiring


def start_converge_worker(app: FastAPI, wiring: SyncWiring, sm: Any) -> ConvergeWorker:
    """Start the timer that converges the vault, shaped like ``RetentionWorker``.

    No interval is passed: the worker re-reads the configured remote's interval
    on every tick, so a user who shortens it in the UI is believed without a
    daemon restart, and a vault with no remote configured ticks harmlessly on
    the default cadence until one appears.
    """
    worker = ConvergeWorker(wiring.service, SqlAlchemySyncRemoteRepo(sm))
    worker.start()
    app.state.converge_worker = worker
    return worker


async def stop_converge_worker(app: FastAPI) -> None:
    """Best-effort teardown, mirroring the retention worker's."""
    worker: ConvergeWorker | None = getattr(app.state, "converge_worker", None)
    if worker is None:
        return
    with contextlib.suppress(TimeoutError, asyncio.CancelledError):
        await asyncio.wait_for(worker.stop(), timeout=2.0)
