"""The reconciler: one loop over every registered target.

ADR one-level-triggered-reconciler-compares-parameters. A pass asks each
target what it wants and what is there, diffs the two including parameters
(:func:`coffer.domain.reconcile.diff`), lets the target's direction policy
decide each difference, and performs the repairable ones. It runs:

- at boot (:meth:`Reconciler.run` with ``Trigger.BOOT``, awaited by the
  lifespan before the daemon reports ready);
- on a fixed period (:meth:`Reconciler.serve`);
- early, for the targets that follow a kind, when a ``Changed`` hint for that
  kind arrives (:meth:`Reconciler.hint`) — an accelerator only: a lost hint
  costs one period, never correctness;
- on demand, for one kind's targets right after the user's own write
  (``Trigger.CHANGE``), after a sync import (``Trigger.IMPORT``), after a
  feature switch (``Trigger.SWITCH``), and for items a person applies from the
  drift view (:meth:`Reconciler.apply`, ``Trigger.MANUAL``).

Rules the loop keeps:

- **Dry-run is pure.** :meth:`plan` computes the same plan and writes
  nothing — no file, no row, no audit event, no hint, not even this object's
  own first-seen bookkeeping.
- **Audit follows the write, in the same call.** A target's ``apply`` writes
  and hands back its audit event; the reconciler records it before moving on.
  If recording fails it runs the target's undo — restoring the content the
  write's backup holds — and reports the item as failed, so the next pass
  retries it.
- **A pass outlives any one target.** A target that raises while being
  planned is reported and skipped; one whose write raises fails that item only.
- **One pass at a time.** Passes are serialised; a pass requested from inside
  a pass (a write that set off another kind's hook) becomes a hint instead of
  waiting on itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import logging
import time
from collections.abc import AsyncIterator, Collection, Sequence
from datetime import UTC, datetime

from coffer.application.audit_service import AuditService
from coffer.application.reconcile.pass_ops import log_report, plan_target, settle_change
from coffer.application.reconcile.ports import ReconcileTarget
from coffer.domain.reconcile import (
    Changed,
    ItemResult,
    Outcome,
    PassReport,
    TargetFailure,
    Trigger,
)

_log = logging.getLogger(__name__)

#: How often a full pass runs with nothing prompting it. Measured on
#: 2026-09-29 (``tests/integration/perf/test_reconcile_pass_cost.py``): a full
#: pass over two agents, twenty skills, a provider and both hooks costs about
#: 27 ms (median; the dry-run plan the same), so the period is set by how long
#: drift may stand unnoticed rather than by cost. A minute keeps "Coffer says installed" and
#: "it works" from disagreeing for longer than a person takes to notice.
DEFAULT_PERIOD_SECONDS = 60.0
#: How long a hint waits for its neighbours, so a burst of writes (an import
#: of twenty rows) costs one pass instead of twenty.
DEFAULT_SETTLE_SECONDS = 0.5
#: A pass slower than this is logged: it is the budget the period was chosen
#: against, and a pass that exceeds it means a target is doing too much.
PASS_BUDGET_SECONDS = 2.0

_in_pass: contextvars.ContextVar[bool] = contextvars.ContextVar("reconcile_in_pass", default=False)


class Reconciler:
    """Owns the registry of targets and the loop that converges them."""

    def __init__(
        self,
        *,
        audit: AuditService,
        period_seconds: float = DEFAULT_PERIOD_SECONDS,
        settle_seconds: float = DEFAULT_SETTLE_SECONDS,
    ) -> None:
        self._audit = audit
        self._period = period_seconds
        self._settle = settle_seconds
        self._targets: dict[str, ReconcileTarget] = {}
        self._lock = asyncio.Lock()
        self._wake = asyncio.Event()
        #: Latest revision hinted per (kind, uid) since the last hinted pass.
        self._pending: dict[tuple[str, str], int] = {}
        #: When each still-open difference was first seen by a writing pass —
        #: the "since" the attention list shows.
        self._first_seen: dict[str, datetime] = {}
        self._last: PassReport | None = None
        self._holder: asyncio.Task[object] | None = None

    # --- registry ------------------------------------------------------------

    def register(self, target: ReconcileTarget) -> None:
        if target.name in self._targets:
            raise ValueError(f"reconcile target {target.name!r} registered twice")
        self._targets[target.name] = target

    @property
    def target_names(self) -> tuple[str, ...]:
        return tuple(self._targets)

    @property
    def period_seconds(self) -> float:
        return self._period

    @property
    def last_pass(self) -> PassReport | None:
        """The most recent writing pass, or ``None`` before the first."""
        return self._last

    @property
    def pending_hints(self) -> dict[tuple[str, str], int]:
        return dict(self._pending)

    def first_seen(self, change_id: str) -> datetime | None:
        return self._first_seen.get(change_id)

    def target_kinds(self, name: str) -> frozenset[str]:
        target = self._targets.get(name)
        return target.kinds if target is not None else frozenset()

    def targets_for_kind(self, kind: str) -> tuple[str, ...]:
        return tuple(n for n, t in self._targets.items() if kind in t.kinds)

    # --- hints ---------------------------------------------------------------

    def hint(self, changed: Changed) -> None:
        """Bring the next pass forward for the targets that follow
        ``changed.kind``. Never blocks and never raises."""
        key = (changed.kind, changed.uid)
        if changed.rev > self._pending.get(key, -1):
            self._pending[key] = changed.rev
        self._wake.set()

    # --- passes --------------------------------------------------------------

    async def plan(
        self, *, targets: Collection[str] | None = None, trigger: Trigger = Trigger.MANUAL
    ) -> PassReport:
        """The plan a pass with ``trigger`` would carry out, computed without
        writing anything."""
        return await self._pass(self._select(targets), trigger, dry_run=True)

    async def run(
        self,
        *,
        targets: Collection[str] | None = None,
        trigger: Trigger,
        actor: str | None = None,
    ) -> PassReport:
        """Run a writing pass now over ``targets`` (default: every one)."""
        names = self._select(targets)
        if _in_pass.get():
            # Asked from inside a pass (a repair's write set off a kind hook):
            # waiting for the lock would wait on ourselves. Defer to a hint.
            for name in names:
                self._pending[("target", name)] = 0
            self._wake.set()
            now = datetime.now(tz=UTC)
            return PassReport(trigger, False, now, now, ())
        return await self._pass(names, trigger, dry_run=False, actor=actor)

    async def apply(self, change_ids: Collection[str], *, actor: str) -> PassReport:
        """Apply the named changes the way a person asked for them
        (``Trigger.MANUAL``). An id that names no current difference, or one
        the policy still will not repair, is reported and not written."""
        wanted = set(change_ids)
        names = tuple(dict.fromkeys(i.split(":", 1)[0] for i in wanted if ":" in i))
        known = tuple(n for n in names if n in self._targets)
        return await self._pass(known, Trigger.MANUAL, dry_run=False, actor=actor, only=wanted)

    @contextlib.asynccontextmanager
    async def hold(self) -> AsyncIterator[None]:
        """Keep every other pass out while a multi-step write is half done.

        A service whose one operation is several writes — a provider switch
        projects, then moves two flags; a sync round applies rows, then asks
        for its import pass — would otherwise let a periodic pass judge the
        state in between and "repair" it back. Passes the holder asks for run
        inside the hold. Re-entrant: inside a pass or a hold it holds nothing
        more, so a repair that goes through such a service cannot wait on
        itself.
        """
        if _in_pass.get() or self._holds():
            yield
            return
        async with self._lock:
            self._holder = asyncio.current_task()
            try:
                yield
            finally:
                self._holder = None

    async def serve(self) -> None:
        """The periodic loop. The boot pass is the lifespan's to await; this
        waits one period (or a hint) before its first pass. Runs until
        cancelled; a pass that fails is logged and the loop carries on."""
        while True:
            hinted = await self._wait()
            try:
                if hinted:
                    await asyncio.sleep(self._settle)
                    names = self._drain_hinted()
                    if names:
                        await self.run(targets=names, trigger=Trigger.HINT)
                else:
                    self._pending.clear()
                    await self.run(trigger=Trigger.PERIOD)
            except asyncio.CancelledError:
                raise
            except Exception:
                _log.exception("reconcile.pass_failed")

    # --- internals -----------------------------------------------------------

    def _select(self, targets: Collection[str] | None) -> tuple[str, ...]:
        if targets is None:
            return tuple(self._targets)
        unknown = [t for t in targets if t not in self._targets]
        if unknown:
            raise KeyError(f"unknown reconcile target(s): {', '.join(sorted(unknown))}")
        return tuple(n for n in self._targets if n in set(targets))

    async def _wait(self) -> bool:
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=self._period)
        except TimeoutError:
            return False
        return True

    def _drain_hinted(self) -> tuple[str, ...]:
        self._wake.clear()
        pending, self._pending = self._pending, {}
        names: set[str] = set()
        for kind, uid in pending:
            if kind == "target":
                names.add(uid)
            else:
                names.update(self.targets_for_kind(kind))
        return tuple(n for n in self._targets if n in names)

    async def _pass(
        self,
        names: Sequence[str],
        trigger: Trigger,
        *,
        dry_run: bool,
        actor: str | None = None,
        only: set[str] | None = None,
    ) -> PassReport:
        started = datetime.now(tz=UTC)
        clock = time.monotonic()
        results: list[ItemResult] = []
        failures: list[TargetFailure] = []
        async with self._locked():
            token = _in_pass.set(True)
            try:
                for name in names:
                    target = self._targets[name]
                    try:
                        changes = await plan_target(target, trigger)
                    except Exception as exc:
                        _log.warning("reconcile.target_failed %s: %r", name, exc)
                        failures.append(TargetFailure(name, repr(exc)))
                        continue
                    for change in changes:
                        if only is not None and change.id not in only:
                            continue
                        results.append(
                            await settle_change(
                                self._audit, target, change, trigger, dry_run=dry_run, actor=actor
                            )
                        )
            finally:
                _in_pass.reset(token)
        report = PassReport(
            trigger=trigger,
            dry_run=dry_run,
            started_at=started,
            finished_at=datetime.now(tz=UTC),
            targets=tuple(names),
            results=tuple(results),
            failures=tuple(failures),
        )
        elapsed = time.monotonic() - clock
        if elapsed > PASS_BUDGET_SECONDS:
            _log.warning("reconcile.pass_over_budget", extra={"seconds": round(elapsed, 3)})
        if not dry_run:
            self._remember(report, names, only is None)
            log_report(report)
        return report

    def _locked(self) -> contextlib.AbstractAsyncContextManager[object]:
        """The pass lock — unless this task already holds it (:meth:`hold`)."""
        if self._holds():
            return contextlib.nullcontext()
        return self._lock

    def _holds(self) -> bool:
        """Whether the running task is the one inside :meth:`hold` — by task,
        not by context, so a task it spawns does not inherit the hold."""
        return self._holder is not None and asyncio.current_task() is self._holder

    def _remember(self, report: PassReport, names: Sequence[str], full: bool) -> None:
        """Keep the first-seen time of every difference still open after the
        pass, and forget those that are gone — for the targets it visited."""
        now = report.finished_at
        open_ids = {r.change.id for r in report.results if r.outcome is not Outcome.APPLIED}
        visited = set(names)
        for cid in list(self._first_seen):
            if cid.split(":", 1)[0] in visited and cid not in open_ids and full:
                del self._first_seen[cid]
        for cid in open_ids:
            self._first_seen.setdefault(cid, now)
        if full:
            self._last = report


__all__ = [
    "DEFAULT_PERIOD_SECONDS",
    "DEFAULT_SETTLE_SECONDS",
    "PASS_BUDGET_SECONDS",
    "Reconciler",
]
