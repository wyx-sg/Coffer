"""The sync service: the thin round behind the daemon's surfaces
(ADR sync-applies-clean-merges-and-stops-on-any-conflict).

The round itself (``round_engine``) is synchronous git work over the vault;
this service is the policy around it: one round at a time, off the event loop,
and every round recorded. Three rules:

- **One lock over every round.** A round holds the service's lock from its
  first git call to its record, so two rounds, an answer and a move never
  interleave.
- **Off the event loop.** Every engine call runs in a worker thread
  (``asyncio.to_thread``); the thread takes the engine's own lock too, so an
  answer recorded from the CLI never interleaves with a round from the timer.
- **Never raises for what a person can be told.** A round that cannot reach
  the remote, cannot use its token, or trips over git is a recorded round with
  a status and a message, never an exception: the worker has no judgement to
  make, and the Sync page shows the same record the history holds.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path

from coffer.application.audit_service import AuditService
from coffer.application.sync import round_answers, round_join, round_resume, round_rollback
from coffer.application.sync.round_engine import RoundEngine
from coffer.application.sync.round_paging import page_rounds
from coffer.application.sync.round_ports import RemoteStorePort, RoundHistoryPort, TokenPort
from coffer.application.sync.service_machines import MachinesMixin
from coffer.application.sync.service_merge import MergeMixin
from coffer.application.sync.service_move import MoveMixin
from coffer.application.sync.service_plaintext import PlaintextMixin
from coffer.application.sync.service_ports import (
    AgentInventoryPort,
    HostMachinePort,
    RemoteProbePort,
    SecretFilesPort,
    VaultMoverPort,
)
from coffer.application.sync.service_remote import RemoteMixin
from coffer.application.sync.service_status import StatusMixin
from coffer.application.sync.views import RollbackView, RoundPage
from coffer.domain.audit import AuditEventType
from coffer.domain.error_base import CofferError
from coffer.domain.secret_errors import SecretBindingPending, SecretMissing
from coffer.domain.sync.errors import SyncNoRemote, SyncRoundNotFound
from coffer.domain.sync.joins import JoinPreview
from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.rounds import APPROVAL_WAIT, RoundRecord, RoundStatus
from coffer.domain.sync.stops import Answer, ConflictFile, Stop

_log = logging.getLogger(__name__)


#: Statuses a round records quietly; everything else is news worth a warning.
_QUIET = frozenset(
    {
        RoundStatus.NOTHING_TO_DO,
        RoundStatus.PULLED,
        RoundStatus.PUSHED,
        RoundStatus.PULLED_AND_PUSHED,
        RoundStatus.JOINED,
        RoundStatus.JOIN_REQUIRED,
    }
)


class SyncService(MoveMixin, PlaintextMixin, RemoteMixin, MachinesMixin, StatusMixin, MergeMixin):
    def __init__(
        self,
        *,
        engine: RoundEngine,
        remotes: RemoteStorePort,
        history: RoundHistoryPort,
        token: TokenPort,
        machine: HostMachinePort,
        secrets: SecretFilesPort,
        probe: RemoteProbePort,
        audit: AuditService,
        set_machine_name: Callable[[str], None],
        vault_path: Callable[[], Path],
        inventory: AgentInventoryPort | None = None,
        mover: VaultMoverPort | None = None,
        after_apply: Callable[[], Awaitable[object]] | None = None,
        hold: Callable[[], contextlib.AbstractAsyncContextManager[object]] | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
        git_available: Callable[[], bool] = lambda: True,
        host_label: Callable[[], str] = lambda: "this machine",
    ) -> None:
        self._engine = engine
        self._remotes = remotes
        self._history = history
        self._token = token
        self._machine = machine
        self._secrets = secrets
        self._probe = probe
        self._audit = audit
        self._set_machine_name = set_machine_name
        self._vault_path = vault_path
        self._inventory = inventory
        self._mover = mover
        self._after_apply = after_apply
        # The reconciler's hold: a round's checkout hints every resource it
        # changed, and a pass that judged the vault before the round's own
        # import pass would undo what another machine switched.
        self._hold = hold or contextlib.nullcontext
        self._lock = asyncio.Lock()
        self._clock = clock
        self._git_available = git_available
        self._host_label = host_label
        self._running_since: str | None = None
        self._next_round_at: str | None = None

    # --- what other parts of the daemon share ---------------------------------

    @property
    def machine_id(self) -> str:
        return self._machine.machine_id()

    def set_next_round(self, when: datetime | None) -> None:
        """The worker says when it will run next (for the status)."""
        self._next_round_at = when.astimezone(UTC).isoformat(timespec="seconds") if when else None

    def remote(self) -> SyncRemote | None:
        return self._remotes.get()

    # --- running engine calls ---------------------------------------------------

    def _now(self) -> str:
        return self._clock().astimezone(UTC).isoformat(timespec="seconds")

    async def _locked[T](self, fn: Callable[[], T]) -> T:
        """``fn`` in a worker thread, under both locks."""

        def call() -> T:
            with self._engine.d.lock:
                return fn()

        async with self._lock:
            return await asyncio.to_thread(call)

    def _required_remote(self) -> SyncRemote:
        remote = self._remotes.get()
        if remote is None:
            raise SyncNoRemote()
        return remote

    async def _round(
        self, name: str, run: Callable[[SyncRemote, str | None], RoundRecord], *, trigger: str
    ) -> RoundRecord:
        """One recorded round: the inventory refreshed, the token resolved,
        ``run`` in a worker thread, and whatever it ended in stored."""
        remote = self._required_remote()
        async with self._hold():
            async with self._lock:
                self._running_since = self._now()
                try:
                    record = await self._attempt(remote, run, trigger)
                finally:
                    self._running_since = None
                stored = await self._history.append(record)
            await self._record(name, stored)
            if stored.applied and self._after_apply is not None:
                # What another machine changed is this machine's warrant to
                # bring its own side effects in step (an active provider's
                # projection, a skill's links): one reconcile pass with the
                # import's warrant, still inside the hold.
                try:
                    await self._after_apply()
                except Exception:
                    _log.warning("sync.after_apply_failed", exc_info=True)
        return stored

    async def _attempt(
        self,
        remote: SyncRemote,
        run: Callable[[SyncRemote, str | None], RoundRecord],
        trigger: str,
    ) -> RoundRecord:
        started = self._now()

        def failed(status: RoundStatus, detail: str) -> RoundRecord:
            return RoundRecord(
                status=status,
                started_at=started,
                finished_at=self._now(),
                trigger=trigger,
                detail=detail,
            )

        if self._inventory is not None:
            try:
                self._machine.set_agents(await self._inventory.inventory())
            except Exception:
                _log.warning("sync.inventory_failed", exc_info=True)
        try:
            token = await self._token.token_for(remote)
        except SecretBindingPending:
            return failed(
                RoundStatus.AUTH_FAILED,
                f"the push token {remote.secret_ref} {APPROVAL_WAIT} "
                "before it may be sent to this remote",
            )
        except SecretMissing:
            return failed(
                RoundStatus.AUTH_FAILED,
                f"the push token {remote.secret_ref} is not stored on this machine",
            )

        try:
            # ``run`` takes the engine's lock itself (every round entry point does).
            return await asyncio.to_thread(run, remote, token)
        except CofferError as exc:
            message = str(exc).replace(token, "***") if token else str(exc)
            return failed(RoundStatus.FAILED, message)

    async def _record(self, name: str, record: RoundRecord) -> None:
        level = logging.DEBUG if record.status in _QUIET else logging.WARNING
        _log.log(level, "sync.%s", name, extra={"status": record.status.value})
        await self._audit.record(
            AuditEventType.SYNC_ROLLED_BACK.value
            if record.status is RoundStatus.ROLLED_BACK
            else AuditEventType.SYNC_RUN.value,
            actor="user" if record.trigger == "manual" else "sync",
            details={
                "round": record.id,
                "status": record.status.value,
                "trigger": record.trigger,
                "pulled": record.pulled_files,
                "pushed": record.pushed_files,
                "conflicts": record.conflicts,
                "held": record.held,
                "join": record.join,
            },
        )

    # --- rounds -----------------------------------------------------------------

    async def run(self, *, trigger: str = "manual") -> RoundRecord:
        """One round now ("Sync now", or the worker's timer)."""
        engine = self._engine
        return await self._round(
            "round", lambda r, t: engine.run(r, t, trigger=trigger), trigger=trigger
        )

    async def join_preview(self) -> JoinPreview:
        """What joining the remote would do, with nothing applied (spec
        vault-sync "Report a join before applying it")."""
        remote = self._required_remote()
        token = await self._token.token_for(remote)
        return await self._locked(lambda: round_join.preview(self._engine, remote, token))

    async def join(self) -> RoundRecord:
        """Join as the preview said: nothing deleted on either side."""
        engine = self._engine
        return await self._round(
            "join", lambda r, t: round_join.join(engine, r, t), trigger="manual"
        )

    async def continue_round(self) -> RoundRecord:
        """Continue a stopped or held round once it is answered."""
        engine = self._engine
        return await self._round(
            "continue", lambda r, t: round_resume.resume(engine, r, t), trigger="manual"
        )

    # --- answers ----------------------------------------------------------------

    async def stop(self) -> Stop | None:
        return await asyncio.to_thread(self._engine.d.state.stop)

    async def answer(self, path: str, choice: Answer) -> Stop:
        return await self._locked(lambda: round_answers.answer(self._engine, path, choice))

    async def open_editor(self, path: str, *, join: bool = False) -> str:
        """The absolute path of ``path``'s hand-merge copy, written when first
        asked for; the OS-open action opens it."""
        return await self._locked(lambda: round_answers.editor_copy(self._engine, path, join=join))

    async def confirm_hold(self) -> Stop:
        return await self._locked(lambda: round_answers.confirm_hold(self._engine))

    async def restore_hold(self, *, actor: str) -> str | None:
        return await self._locked(lambda: round_answers.restore_held(self._engine, actor=actor))

    async def join_choices(self) -> tuple[ConflictFile, ...]:
        return await asyncio.to_thread(self._engine.d.state.join_choices)

    async def choose(
        self, choices: list[tuple[str, Answer]], *, actor: str
    ) -> tuple[ConflictFile, ...]:
        """Settle a join's differing files, one or several at once."""

        def apply() -> tuple[ConflictFile, ...]:
            remaining = self._engine.d.state.join_choices()
            for path, choice in choices:
                remaining = round_answers.choose_join(self._engine, path, choice, actor=actor)
            return remaining

        return await self._locked(apply)

    # --- history and rollback ----------------------------------------------------

    async def last_round(self) -> RoundRecord | None:
        found = await self._history.recent(1)
        return found[0] if found else None

    async def rounds(self, *, limit: int, cursor: str | None = None) -> RoundPage:
        """One page of the history, newest first. Keyset, not offset: a round
        finishing at the head between two reads must not shift later pages."""
        return await page_rounds(self._history, limit, cursor)

    async def round(self, round_id: int) -> RoundRecord:
        found = await self._history.get(round_id)
        if found is None:
            raise SyncRoundNotFound(round_id)
        return found

    async def _rollable(self, round_id: int) -> RoundRecord:
        record = await self.round(round_id)
        if record.status is RoundStatus.ROLLED_BACK:
            raise round_rollback.SyncNothingToRollBack(
                "this round is itself a rollback; its snapshot is already in place"
            )
        return record

    async def rollback_plan(self, round_id: int) -> RollbackView:
        record = await self._rollable(round_id)
        shown = await self._locked(lambda: round_rollback.plan(self._engine, record))
        times = {name: when for name, _commit, when in self._engine.d.git.snapshots()}
        when = times.get(shown.snapshot)
        return RollbackView(
            snapshot=shown.snapshot,
            snapshot_commit=shown.snapshot_commit,
            snapshot_time=datetime.fromtimestamp(when, tz=UTC).isoformat(timespec="seconds")
            if when
            else None,
            reverses=shown.reverses,
            kept=shown.kept,
        )

    async def rollback(self, round_id: int, *, actor: str) -> RoundRecord:
        """Put back what round ``round_id`` changed, as a new commit here; the
        next round pushes it (spec vault-sync "Snapshot before checking out
        and roll a round back from it")."""
        record = await self._rollable(round_id)
        async with self._hold():
            async with self._lock:
                done = await asyncio.to_thread(
                    _with_lock,
                    self._engine,
                    lambda: round_rollback.rollback(self._engine, record, actor=actor),
                )
                stored = await self._history.append(done)
            await self._record("rollback", stored)
        return stored


def _with_lock[T](engine: RoundEngine, fn: Callable[[], T]) -> T:
    with engine.d.lock:
        return fn()


__all__ = ["SyncService"]
