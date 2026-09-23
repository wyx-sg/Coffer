"""One converge round (spec vault-sync "Run the seven round steps in order").

The order of the seven steps is the most important thing in this module, and
it is the whole reason the 2026-07-10 mutual deletion cannot happen again::

    0  Repair    — working tree back to the pointer if it drifted, and
                    refuse a remote whose layout this build does not know
    1  Serialize — export the vault into the tree, commit as L
    2  Merge     — fetch, three-way-merge origin into L → M
    3  Diff      — D := L..M, exactly what the remote contributed
    4  Guard     — deletion guard, both directions; snapshot L
    5  Apply     — D onto the vault, path by path
    6  Publish   — push M, advance the pointer

**Why local state is committed before the merge.** Pulling first fast-forwards
a tree that has no local commit, so git is never given the three inputs a
three-way merge needs, and applying the remote's changes silently overwrites
whatever this vault changed on the same path. Committing first gives git base
``P``, local ``L`` and remote ``R``; the diff ``L..M`` is then precisely the
remote's contribution, and the vault — which equals ``L`` at that moment —
lands on ``M`` with its own edits intact.

**Why deletion is safe.** A deletion reaches ``D`` only because some machine
deleted that document relative to a shared base. A machine that merely *lacks*
a document makes no change relative to its own base, and git reads "unchanged"
as an assertion about nothing. The previous design could not say this, because
its export rewrote the tree from local state wholesale.

The round returns a ``ConvergeRun`` for every **outcome**, so the worker's loop
never decides what is survivable. The two exceptions are refusals rather than
outcomes — a base that cannot be established (``SYNC_JOIN_AMBIGUOUS``) and a
remote layout this build does not know (``SYNC_BUNDLE_TOO_NEW``) — and they
raise, because what the surfaces owe the user there is a code and a next step,
not a diff. ``ConvergeService.run_once`` records them as failed rounds, so the
loop is still spared the judgement.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime

from coffer.application.sync.conflicts import ConflictArbiter
from coffer.application.sync.convergence_backwards import BackwardsMixin
from coffer.application.sync.convergence_ops import (
    apply_diff,
    breached,
    commit_message,
    diff_between,
    failed_run,
    hold_round,
    outstanding_holds,
    readmit_applicable,
    reconcile,
    refuse_newer_layout,
    release_hold,
    remote_tip,
    snapshot,
)
from coffer.application.sync.convergence_preview import PreviewMixin
from coffer.application.sync.joining import JoinResolver
from coffer.application.sync.ports import (
    ConvergenceStatePort,
    CredentialSyncPort,
    GitMirrorPort,
    PostImportHook,
    VaultApplyPort,
)
from coffer.domain.error_base import CofferError
from coffer.domain.sync.convergence import (
    ConvergeRun,
    ConvergeStatus,
    GuardDirection,
    JoinKind,
    PendingConfirmation,
)
from coffer.domain.sync.diff import DeletionGuard, DiffSummary
from coffer.domain.sync.models import ExportSummary

_logger = logging.getLogger(__name__)


class ConvergeRound(BackwardsMixin, PreviewMixin):
    """Runs one round against one already-prepared working tree.

    Deliberately not the service: the service owns the remote's configuration,
    the lock and the audit trail, while this owns the algorithm. Keeping them
    apart is what lets the algorithm be tested against a fake mirror without a
    database anywhere near it.
    """

    def __init__(
        self,
        *,
        mirror: GitMirrorPort,
        state: ConvergenceStatePort,
        appliers: Sequence[VaultApplyPort],
        arbiter: ConflictArbiter,
        joining: JoinResolver,
        serialize: Callable[[], Awaitable[ExportSummary]],
        guard: DeletionGuard,
        branch: str,
        credentials: CredentialSyncPort,
        post_import: Sequence[PostImportHook] = (),
    ) -> None:
        self._mirror = mirror
        self._state = state
        self._appliers = {a.prefix: a for a in appliers}
        self._arbiter = arbiter
        self._joining = joining
        self._serialize = serialize
        self._guard = guard
        self._branch = branch
        self._post_import = list(post_import)
        self._credentials = credentials

    async def run(
        self,
        *,
        token: str | None,
        join_choice: str | None = None,
        confirmed: PendingConfirmation | None = None,
        adopt: bool = False,
    ) -> ConvergeRun:
        """One round. It joins the remote only when ``adopt`` says to.

        ``confirmed`` is a hold the user accepted. The round is re-derived
        rather than resumed — serialization is deterministic, so an unchanged
        vault against an unchanged remote yields the diff they were shown — and
        the guard is waived for **that direction only**, and only while the
        remote still stands where the hold was raised. A "yes, publish my
        deletions" is not a "yes, apply whatever the remote dropped", and it is
        not a standing permission that survives the remote moving.

        A hold this vault is already carrying is deliberately **not**
        short-circuited on. It is an unanswered question about one diff, so the
        round re-derives that diff, releases the hold where the breach is gone
        (``release_hold``) and otherwise re-states the same question rather
        than raising a fresh one (``hold_round``).
        """
        started = datetime.now(tz=UTC)
        if not adopt and await self.is_joining():
            # Detection runs on every round without a pointer; applying is
            # explicit (spec vault-sync). So the join is resolved and reported,
            # read-only, and nothing is applied or pushed until ``adopt``.
            report = await self.preview_join(token=token)
            return ConvergeRun(
                status=ConvergeStatus.AWAITING_JOIN,
                started_at=started,
                finished_at=datetime.now(tz=UTC),
                join=report.kind,
                join_report=report,
            )
        pointer, join = await self._base(join_choice, token=token)

        # The fetch happens HERE, before anything compares against the remote.
        # It used to sit below, which made the waiver check meaningless: it
        # read a remote-tracking ref this round had not updated, so "has the
        # remote moved?" could only ever answer no, and a confirmation went on
        # to authorise deletions that arrived after the user looked.
        await self._mirror.fetch(token=token)
        # Nothing has touched the vault or the tree yet, which is the only
        # place this check belongs: a remote written in a layout this build
        # does not know is refused before the round can either apply it or
        # publish over it.
        await refuse_newer_layout(self._mirror, f"origin/{self._branch}")
        waived = await self._waived_direction(confirmed)

        # --- 1 serialize ---------------------------------------------------
        local = await self._serialize_and_commit(pointer)
        published = await diff_between(self._mirror, pointer, local)

        breach = (
            []
            if waived is GuardDirection.PUBLISH
            else await breached(self._mirror, self._guard, published, pointer)
        )
        if breach:
            return await self._hold(started, GuardDirection.PUBLISH, local, published, breach)
        await release_hold(self._state, GuardDirection.PUBLISH)

        # --- 2 merge -------------------------------------------------------
        try:
            merged, resolved, unresolved = await self._merge(local)
        except CofferError as e:
            return failed_run(started, str(e))
        if unresolved:
            # The vault is untouched and the pointer has not moved: two
            # machines waiting is better than two machines quietly disagreeing.
            return ConvergeRun(
                status=ConvergeStatus.CONFLICT,
                started_at=started,
                finished_at=datetime.now(tz=UTC),
                join=join,
                conflicts=tuple(unresolved),
                agent_resolved=tuple(resolved),
            )

        # --- 3 diff --------------------------------------------------------
        applied = await diff_between(self._mirror, local, merged)
        # The retry set is applied alongside the diff, so the guard must see
        # it too: a held path the tree has since dropped is a deletion this
        # round is about to perform, and a guard that only looked at ``D``
        # would let any number of those through unasked.
        await readmit_applicable(self._appliers, self._state)
        retried = await outstanding_holds(self._mirror, self._state, applied)
        everything = DiffSummary.of(
            [*applied.changes, *retried.changes],
            # The retry set has no pairings of its own — it is reconstructed
            # from held paths rather than read out of a diff — so the incoming
            # diff's are the whole of what the guard has to go on here.
            applied.renames,
        )

        # --- 4 guard + snapshot --------------------------------------------
        breach = (
            []
            if waived is GuardDirection.APPLY
            else await breached(self._mirror, self._guard, everything, local)
        )
        if breach:
            return await self._hold(started, GuardDirection.APPLY, merged, everything, breach)
        await release_hold(self._state, GuardDirection.APPLY)
        await snapshot(self._mirror, local)

        # --- 5 apply -------------------------------------------------------
        not_applicable: list[str] = []
        failures = await self.apply(applied, not_applicable=not_applicable)
        failures.extend(await self.apply(retried, not_applicable=not_applicable))
        failures.extend(await reconcile(self._post_import, applied))
        # Ciphertext travels whatever the keys; a ref this machine now holds
        # but cannot open is named, never left to fail at first use (spec
        # vault-sync "Report refs without a key as locked").
        locked = await asyncio.to_thread(self._credentials.locked_refs)

        # --- 6 publish ------------------------------------------------------
        status = ConvergeStatus.OK if (published or applied) else ConvergeStatus.NO_CHANGE
        try:
            await self._mirror.push(branch=self._branch, token=token)
        except CofferError as e:
            # The commit stays. Local history is the first layer of recovery
            # and the next round carries what is outstanding.
            status = ConvergeStatus.PUSH_FAILED
            _logger.warning("converge: push failed, commit retained: %s", e)
        await self._state.set_pointer(merged)

        return ConvergeRun(
            status=status,
            started_at=started,
            finished_at=datetime.now(tz=UTC),
            join=join,
            applied=applied,
            published=published,
            commit=merged,
            agent_resolved=tuple(resolved),
            failures=tuple(failures),
            not_applicable=tuple(not_applicable),
            locked_refs=tuple(locked),
        )

    async def _waived_direction(
        self, confirmed: PendingConfirmation | None
    ) -> GuardDirection | None:
        """Which guard direction this round may skip, if any.

        Only the direction the user actually answered, and only while the
        remote still stands where the hold was raised. A hold whose recorded
        tip is unknown (the remote had no branch yet) waives nothing — the
        conservative direction, because an unknown tip cannot be shown to be
        the one the user looked at.
        """
        if confirmed is None or confirmed.remote_tip is None:
            return None
        if confirmed.remote_tip != await remote_tip(self._mirror, self._branch):
            return None
        return confirmed.direction

    # --- steps --------------------------------------------------------------

    async def _base(
        self, choice: str | None = None, *, token: str | None = None
    ) -> tuple[str, JoinKind | None]:
        """Step 0. The pointer, recovering or establishing it when absent.

        A round with no pointer is joining, and the two kinds of joiner need
        opposite treatment — which is why this runs here rather than inside the
        ``adopt`` command: configuring a remote on a machine that forgot its
        pointer must not be able to route around the distinction.
        """
        pointer = await self._state.pointer()
        if pointer is not None and not await self._reachable(pointer):
            # The working tree was deleted, or moved, and the fresh repository
            # has never seen this commit. Every later round would fail on
            # ``git diff <gone>`` forever, with rebuild — which discards
            # everything only this machine holds — as the sole escape. A base
            # that no longer exists is no base, so this machine is joining, and
            # the registry will recognise it as returning and hand back a base
            # that does exist.
            _logger.warning("converge: pointer %s is unreachable; re-joining", pointer[:12])
            await self._state.clear_pointer()
            pointer = None
        if pointer is None:
            # The distinction is read out of the remote's registry, so the
            # remote has to be in hand before the question can be asked. The
            # ordinary round fetches later, but a joining machine is precisely
            # the one whose working tree may have just been re-created empty —
            # a reinstall took it — and an unfetched repository has no
            # ``origin/<branch>`` to read a descriptor from. Answering "new"
            # from a missing ref is how a returning machine republishes
            # everything the others deleted while it was away.
            await self._mirror.fetch(token=token)
            join = await self._joining.resolve(self._mirror, choice=choice)
            await self._state.set_pointer(join.pointer)
            if join.kind is JoinKind.RETURNING:
                # The tree must stand at the recovered base, or the merge below
                # has no common ancestor: git falls back to an unrelated-history
                # union, in which a deletion cannot be expressed at all. The
                # live vault is untouched by this — the working tree is a
                # serialization target, and step 1 rewrites it from the vault.
                await self._mirror.reset_hard(join.pointer)
            return join.pointer, join.kind
        head = await self._mirror.head()
        if head is not None and head != pointer and pointer != self._mirror.EMPTY_TREE:
            # A crashed round left the tree somewhere unexpected. Serializing
            # onto it would turn "this vault never absorbed that" into "this
            # vault deleted that" the moment the diff is taken.
            #
            # Two pointers are deliberately not repaired to. The empty tree is
            # not a commit at all — it is the base a machine joining as new
            # diffs against, and git cannot reset to it — and a round that left
            # it in place absorbed nothing, so there is nothing to return to. An
            # unborn HEAD is the same fact from the other side: the tree holds no
            # commit yet, so there is nothing that could have drifted.
            await self._mirror.reset_hard(pointer)
        return pointer, None

    async def _serialize_and_commit(self, pointer: str) -> str:
        """Step 1. The vault into the tree, committed only if it moved."""
        summary = await self._serialize()
        if not await self._mirror.stage_all():
            return pointer
        return await self._mirror.commit(commit_message(summary))

    async def _merge(self, local: str) -> tuple[str, list[str], list[str]]:
        """Step 2. git merges; the arbiter handles only what it cannot.

        A remote with no branch yet — the first machine to converge with a
        freshly created repository — has nothing to merge, and asking git to
        merge a ref that does not exist is an error rather than an empty merge.
        There is no remote contribution in that case, so the round carries on
        with ``L`` and publishes it.
        """
        if await remote_tip(self._mirror, self._branch) is None:
            return local, [], []
        conflicts = await self._mirror.merge(f"origin/{self._branch}", message="coffer converge")
        if not conflicts:
            head = await self._mirror.head()
            return head or local, [], []
        resolved, unresolved = await self._arbiter.arbitrate(self._mirror, conflicts)
        if unresolved:
            await self._mirror.abort_merge()
            return local, resolved, unresolved
        merged = await self._mirror.commit_merge("coffer converge (merge)")
        return merged, resolved, []

    async def apply(
        self, diff: DiffSummary, *, not_applicable: list[str] | None = None
    ) -> list[tuple[str, str]]:
        """Step 5. Each path, independently; a failure is reported, not fatal.

        A path that fails is *held*: the exporter must not delete it next
        round, because "this vault could not absorb it" is not "the user
        deleted it" — which is the same confusion the whole design exists to
        prevent, arriving through a different door. A path that can never apply
        here is held too, but it is not a failure: it goes to ``not_applicable``.
        """
        return await apply_diff(self._appliers, self._state, diff, not_applicable)

    async def _hold(
        self,
        started: datetime,
        direction: GuardDirection,
        commit: str,
        diff: DiffSummary,
        breaches: list[tuple[str, int, int]],
    ) -> ConvergeRun:
        """Step 4's refusal, with the remote and this vault's state to hand."""
        return await hold_round(
            self._mirror,
            self._state,
            branch=self._branch,
            started=started,
            direction=direction,
            commit=commit,
            diff=diff,
            breaches=breaches,
        )
