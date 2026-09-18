"""Pieces of one converge round that need nothing from the round itself.

Extracted to keep ``convergence.py`` under the project's file-size limit,
following the same pattern as ``resource_delete_ops.py`` beside
``resource_service.py``. Everything here is a free function over values the
round already has: the outcome objects it returns, how a failure is classified,
what a commit says about itself, and the post-apply hook sweep. The **order of
the seven steps** — the part of this design that is load-bearing — stays in
``convergence.py`` where it can be read in one screen.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from coffer.application.sync.ports import (
    ConvergenceStatePort,
    GitMirrorPort,
    PostImportHook,
    VaultApplyPort,
)
from coffer.domain.error_base import CofferError
from coffer.domain.sync.convergence import (
    ConvergeRun,
    ConvergeStatus,
    GuardDirection,
    PendingConfirmation,
)
from coffer.domain.sync.diff import ChangeStatus, DeletionGuard, DiffSummary, DocChange
from coffer.domain.sync.manifest import MANIFEST_PATH, refuse_if_too_new
from coffer.domain.sync.models import ExportSummary

_logger = logging.getLogger(__name__)

#: Error codes that mean "this document is not for this machine" rather than
#: "not yet". An ``agent`` whose ``config_dir`` does not exist here will never
#: apply, and retrying it every round would turn a fact about this machine into
#: a permanent error the user learns to ignore.
_INAPPLICABLE_CODES = frozenset({"AGENT_CONFIG_DIR_MISSING", "KIND_NOT_APPLICABLE"})


def is_inapplicable(error: Exception) -> bool:
    """Whether a failure means "not for this machine" rather than "not yet"."""
    return getattr(error, "code", "") in _INAPPLICABLE_CODES


def commit_message(summary: ExportSummary) -> str:
    """A message naming the counts per area.

    The history is meant to be read with the user's own git tools, so it says
    what changed in vault terms rather than repeating a timestamp the commit
    already carries.
    """
    counts = " ".join(f"{a.area}={a.count}" for a in summary.areas)
    return f"coffer: {counts}" if counts else "coffer"


def held_run(
    started: datetime, pending: PendingConfirmation, *, already_reported: bool = False
) -> ConvergeRun:
    """A round stopped at the deletion guard, waiting on the user."""
    return ConvergeRun(
        status=ConvergeStatus.AWAITING_CONFIRMATION,
        started_at=started,
        finished_at=datetime.now(tz=UTC),
        pending=pending,
        hold_already_reported=already_reported,
    )


def _same_question(before: PendingConfirmation, now: PendingConfirmation) -> bool:
    """Whether two holds put the same question to the user.

    Direction, remote tip, breaches and paths — everything the surfaces show
    and everything a confirmation would authorise. The local commit is
    deliberately not compared: it is *how* a confirmation resumes, not what it
    is about, and it moves whenever the vault does while the question stands.
    """
    return (
        before.direction is now.direction
        and before.remote_tip == now.remote_tip
        and before.breaches == now.breaches
        and before.paths == now.paths
    )


async def hold_round(
    mirror: GitMirrorPort,
    state: ConvergenceStatePort,
    *,
    branch: str,
    started: datetime,
    direction: GuardDirection,
    commit: str,
    diff: DiffSummary,
    breaches: list[tuple[str, int, int]],
) -> ConvergeRun:
    """Step 4's refusal: record what the guard stopped and wait on the user.

    A round re-derives its diff every time (spec vault-sync FR-091), so a
    question the user has not answered yet arrives here again on every tick —
    and the second arrival is not news. Whatever hold this vault is already
    carrying is read back here and compared: the same question is stored as the
    same hold, keeping the moment the user was asked, and the run is marked as
    already reported so the recording coalesces onto the one row and the log
    says it once (FR-092).

    The commit *is* refreshed, because it is the revision a confirmation would
    resume from and the vault may have moved under a question that did not.
    """
    outstanding = await state.pending()
    pending = PendingConfirmation(
        direction=direction,
        commit=commit,
        remote_tip=await remote_tip(mirror, branch),
        breaches=tuple(breaches),
        # What the round would remove, which is not every deleted path: a
        # document whose content reappears elsewhere in the same diff moved,
        # and the guard does not count it, so the user is not asked about it.
        paths=diff.lost_paths(),
        raised_at=datetime.now(tz=UTC),
    )
    again = outstanding is not None and _same_question(outstanding, pending)
    if again and outstanding is not None:
        pending = dataclasses.replace(pending, raised_at=outstanding.raised_at)
    await state.set_pending(pending)
    return held_run(started, pending, already_reported=again)


async def release_hold(state: ConvergenceStatePort, direction: GuardDirection) -> None:
    """Drop an outstanding hold whose guard direction now passes.

    The latch records a decision about a specific diff, and this round has just
    re-derived that diff and found nothing over the threshold in the direction
    the hold was raised for. The reason the user was asked is gone, so the
    question goes with it and the round carries on — which is how a vault held
    by a defect that has since been fixed unsticks itself instead of waiting
    for someone to notice and press a button.

    Only the direction that passed. A hold raised on the publish side says
    nothing about what the remote has since dropped, and a round that has
    cleared one guard has not yet reached the other.
    """
    outstanding = await state.pending()
    if outstanding is None or outstanding.direction is not direction:
        return
    _logger.info(
        "converge: releasing the %s hold raised at %s; its diff no longer breaches the guard",
        direction.value,
        outstanding.raised_at.isoformat(),
    )
    await state.set_pending(None)


def failed_run(started: datetime, error: str) -> ConvergeRun:
    """A round that could not complete. The vault is untouched."""
    return ConvergeRun(
        status=ConvergeStatus.FAILED,
        started_at=started,
        finished_at=datetime.now(tz=UTC),
        error=error,
    )


async def reconcile(hooks: Sequence[PostImportHook], diff: DiffSummary) -> list[tuple[str, str]]:
    """Step 5b. Each kind re-applies its machine-local side effects.

    A resource row is only half of what a kind owns: the other half is a native
    config file, a shim, a delivered skill — things that live outside the vault,
    differ per machine, and therefore cannot travel. The applier writes the row;
    the hook makes this machine's side of it match again (spec vault-sync
    ``## Applying a diff``).

    It runs from **current state**, not from the diff, which is why it runs once
    for the whole round rather than per path, and why it is safe to run after
    some paths failed. A round that applied nothing skips it: there is no work,
    and a hook reporting a pre-existing local problem should not turn an idle
    round into a round with failures.
    """
    if not diff.vault_changes or not hooks:
        return []
    failures: list[tuple[str, str]] = []
    for hook in hooks:
        try:
            errors = await hook.reconcile()
        except Exception as e:
            # A kind module's reconciliation is machine-local housekeeping. It
            # has no business failing a round that already landed.
            _logger.warning("converge: post-import hook %s raised: %s", hook.kind, e)
            failures.append((f"{hook.kind}/", str(e)))
            continue
        failures.extend((f"{hook.kind}/", error) for error in errors)
    return failures


#: Pre-apply snapshot tags. The tree of the commit a round tags here is by
#: construction the vault's state immediately before its apply, so a rollback is
#: the round's own machinery run backwards (spec vault-sync ``## Safety``).
SNAPSHOT_PREFIX = "coffer/pre-apply/"
SNAPSHOTS_KEPT = 10


async def snapshot(mirror: GitMirrorPort, commit: str) -> None:
    """Step 4. Tag the vault's state as it stands just before the apply."""
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    await mirror.tag(f"{SNAPSHOT_PREFIX}{stamp}", commit)
    for stale in (await mirror.tags(SNAPSHOT_PREFIX))[SNAPSHOTS_KEPT:]:
        await mirror.delete_tag(stale)


async def breached(
    mirror: GitMirrorPort, guard: DeletionGuard, diff: DiffSummary, at: str
) -> list[tuple[str, int, int]]:
    """Areas whose deletions exceed the guard, as ``(area, deleted, total)``.

    The denominators are read at the commit the diff starts from rather than
    from the working tree, so a round already in flight cannot move them under
    the check.
    """
    deleted_areas = {c.area for c in diff.vault_changes if c.status is ChangeStatus.DELETED}
    if not deleted_areas:
        return []
    totals = {area: await mirror.file_count(at, f"{area}/") for area in deleted_areas}
    return guard.breached_areas(diff.vault_changes, totals)


async def outstanding_holds(
    mirror: GitMirrorPort, state: ConvergenceStatePort, applied: DiffSummary
) -> DiffSummary:
    """Step 5a. The retry set, as a diff the round can apply.

    A path this vault failed to absorb is *pending*, not failed once and
    forgotten (spec vault-sync ``## The pointer advances only on absorption``):
    it is re-attempted next round and leaves the set on success. The incoming
    diff alone cannot do that — a held path is unchanged in every later diff,
    precisely because the failure was local — so the set is walked directly.

    The **not-applicable** set is deliberately left out. Those paths cannot
    apply on this machine at all; retrying them every round would turn a fact
    about this machine into a recurring error.

    Whether a held path is an upsert or a removal is answered by the working
    tree rather than remembered: the tree is the merged truth this vault is
    trying to reach, and a path deleted there since should be absorbed as the
    deletion it now is.
    """
    retry, _not_applicable = await state.held_paths()
    pending = sorted(retry - {c.path for c in applied.vault_changes})
    if not pending:
        return DiffSummary()
    return DiffSummary.of(
        [
            DocChange(
                path,
                ChangeStatus.MODIFIED
                if await mirror.read_worktree(path) is not None
                else ChangeStatus.DELETED,
            )
            for path in pending
        ]
    )


async def remote_tip(mirror: GitMirrorPort, branch: str) -> str | None:
    """The remote's current tip, or None when there is not one yet.

    None on a virgin remote, and None is the safe answer: a hold recorded
    against "unknown" makes a later confirmation re-check the deletion guard
    instead of waiving it.
    """
    try:
        return await mirror.resolve_revision(f"origin/{branch}")
    except CofferError:
        return None


def applier_for(appliers: Mapping[str, VaultApplyPort], path: str) -> VaultApplyPort | None:
    """The applier owning a bundle path, or None when no area claims it.

    None is ordinary, not an error: ``machines/`` and ``manifest.json`` are in
    every diff and belong to no applier, because the registry is read from the
    tree and the manifest says nothing about vault state.
    """
    for prefix, applier in appliers.items():
        if path.startswith(prefix):
            return applier
    return None


async def refuse_newer_layout(mirror: GitMirrorPort, revision: str) -> None:
    """Step 0b. Stop before reading a tree written in a layout this build does
    not know (spec vault-sync; ``SYNC_BUNDLE_TOO_NEW``).

    ``revision`` is the commit whose documents are about to be read — the
    remote's tip for a round, the tip for a rebuild, the named point for a
    restore — because that is the tree whose layout has to be legible, not
    whatever the working tree happens to hold.

    It runs before the round serializes, merges, applies or pushes anything, so
    a refusal leaves both sides exactly as they were. Both sides is the point:
    the older build would not only apply a tree it half-understands, it would
    *publish* into it — every area the exporter converges is written from what
    this build knows, so a newer build's documents in a directory this one
    writes would leave as deletions nobody made, and the other machines would
    honour them.

    It **raises** rather than returning a status, unlike the rest of a round's
    outcomes and for the same reason ``SyncJoinAmbiguous`` does: the surfaces
    answer this with a code (409) and an instruction to upgrade, not with a
    diff. ``ConvergeService.run_once`` turns it into a recorded ``FAILED`` run,
    so the worker's loop still has no judgement to make.
    """
    refuse_if_too_new(await mirror.read_file(revision, MANIFEST_PATH))
