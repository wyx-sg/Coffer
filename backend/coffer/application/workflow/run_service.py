"""``WorkflowRunService`` — a run's own lifecycle (spec workflow).

Create, read, list, delete, the four signals, and the projection rebuild the
daemon performs at start. Everything about a NODE lives in
``node_service``; the split is the one ``plan.md`` names, and it is also the
line the file-size ceiling falls on.

What this service does not do: advance the run. ``start`` moves the run to
``running`` and stops there — the advancer notices and dispatches the first
node. A service that started the node itself would make "the run advances on
its own" a property of whoever happened to call ``start``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any, Protocol
from uuid import uuid4

from coffer.application.workflow.commands import (
    DEFAULT_ACTOR,
    SYSTEM_ACTOR,
    CommandResult,
    PendingEvent,
    RunCommands,
    parse_snapshot,
    utcnow,
)
from coffer.application.workflow.ports import (
    ApprovalRepoPort,
    ArtifactStorePort,
    AttemptRepoPort,
    AuditPort,
    EventRepoPort,
    MachineIdPort,
    RunRepoPort,
    RunRow,
)
from coffer.application.workflow.run_label_ops import KEEP, KeepStored
from coffer.domain.audit import AuditEventType
from coffer.domain.resource import Resource
from coffer.domain.workflow.errors import TemplateDisabled
from coffer.domain.workflow.events import EventActor, EventType
from coffer.domain.workflow.run import (
    FailureReason,
    NodeStatus,
    RunSignal,
    RunStatus,
)
from coffer.domain.workflow.transitions import apply_run_signal

_logger = logging.getLogger(__name__)


#: Which event a signal writes. ``abort`` is the only one that also touches
#: another table (its pending approvals are superseded), which is why the map
#: is data and the abort case is code.
_SIGNAL_EVENT: dict[RunSignal, EventType] = {
    RunSignal.START: EventType.RUN_STARTED,
    RunSignal.PAUSE: EventType.RUN_PAUSED,
    RunSignal.RESUME: EventType.RUN_RESUMED,
    RunSignal.ABORT: EventType.RUN_ABORTED,
}


class TemplateSourcePort(Protocol):
    """Where a template resource is read from at run creation.

    Declared here rather than in ``ports`` because it is not a seam to another
    kind: it is the resource framework, which this layer is a kind of.
    ``ResourceService.get`` satisfies it structurally, and a test satisfies it
    with three lines. It takes the template's **uid**, because that is a
    resource's identity — a run started from a template the developer renames
    an hour later was still started from that template.
    """

    async def get(self, uid: str) -> Resource: ...


class WorkflowRunService:
    """Commands that act on a run as a whole."""

    def __init__(
        self,
        *,
        runs: RunRepoPort,
        events: EventRepoPort,
        attempts: AttemptRepoPort,
        approvals: ApprovalRepoPort,
        artifacts: ArtifactStorePort,
        machine: MachineIdPort,
        audit: AuditPort,
        templates: TemplateSourcePort,
        default_agent: str,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._runs = runs
        self._approvals = approvals
        self._artifacts = artifacts
        self._attempts = attempts
        self._audit = audit
        self._templates = templates
        self._default_agent = default_agent
        self._clock = clock
        self._cmd = RunCommands(
            runs=runs, events=events, attempts=attempts, machine=machine, clock=clock
        )

    # -- reads ------------------------------------------------------------

    async def get_run(self, run_id: str) -> RunRow:
        return await self._cmd.require_run(run_id)

    async def list_runs(
        self, *, status: str | None = None, limit: int | None = None
    ) -> Sequence[RunRow]:
        return await self._runs.list_runs(status=status, limit=limit)

    def owned_here(self, run: RunRow) -> bool:
        """What the API reports as ``owned_here`` (FR-012)."""
        return run.machine_id == self._cmd.machine_id

    # -- creation ---------------------------------------------------------

    async def create_run(
        self,
        *,
        template_uid: str,
        title: str,
        agent: str | None = None,
        actor: EventActor = DEFAULT_ACTOR,
    ) -> RunRow:
        """Freeze a template and record the run.

        **A template and a title, and nothing else** (FR-011). Two things the
        developer used to supply are gone: the working directory, which Coffer
        now makes and owns per run (FR-053), and the inputs, which are added
        afterwards through ``WorkflowInputsService`` at any point in the run's
        life (FR-050). Both were questions asked before the developer had
        thought about the work.

        The snapshot is taken here and never consulted again (FR-010): every
        later read of "what is this run supposed to do" goes to
        ``template_snapshot``, so editing the template afterwards cannot reach
        a run already created.

        **No conversation is opened.** A run has none of its own (FR-030) —
        every conversation belongs to one task and is opened by the driver when
        that task starts, so a run created and never started has spent nothing
        and left no empty thread behind for the developer to wonder about.
        """
        resource = await self._templates.get(template_uid)
        # Enabled decides whether a workflow starts new runs (FR-066), and the
        # decision is made here so that it holds for the CLI and the API as
        # well as for the dropdown that also hides it.
        if not resource.enabled:
            raise TemplateDisabled(resource.name)
        snapshot: dict[str, Any] = dict(resource.config)
        # Parsed once at creation so a template stored before a validation rule
        # existed is refused HERE, naming the field, rather than stalling the
        # run the first time the advancer reads it.
        parsed = parse_snapshot(snapshot)

        run_id = uuid4().hex
        agent_key = agent or self._default_agent
        # Before the row, because ``workdir`` is derived from the directory
        # this creates and a run whose recorded workdir does not exist is a
        # node that cannot open a conversation.
        self._artifacts.ensure_run_dirs(run_id)
        workdir = self._artifacts.workspace_dir(run_id)
        run = await self._runs.create_run(
            run_id=run_id,
            title=title,
            workdir=workdir,
            machine_id=self._cmd.machine_id,
            template_snapshot=snapshot,
            # The template's LABEL as it read at this moment, not its
            # identity: this is provenance for a person to recognise, it is
            # rendered raw as the run's subtitle, and it is allowed to dangle
            # (FR-010 — the snapshot beside it is what the run actually
            # executes). Freezing the label is what makes it still answer
            # "what was this started from" after the template is renamed or
            # deleted, which an identity nothing resolves any more would not.
            template_ref=resource.name,
            status=RunStatus.DRAFT.value,
            inputs=[],
            now=self._clock(),
        )
        # Appended, but no projection write follows: a freshly inserted row
        # already holds exactly what ``project([run.created])`` produces, and
        # writing it would bump the run to version 2 before any client has seen
        # version 1.
        await self._cmd.append(
            run_id,
            PendingEvent(
                event_type=EventType.RUN_CREATED,
                payload={
                    "template": run.template_ref,
                    "title": title,
                    "workdir": workdir,
                    "agent": agent_key,
                    "stages": [stage.key for stage in parsed.stages],
                },
            ),
            actor,
        )
        return run

    # -- signals ----------------------------------------------------------

    async def signal(
        self,
        run_id: str,
        signal: RunSignal,
        *,
        version: int,
        reason: str | None = None,
        actor: EventActor = DEFAULT_ACTOR,
    ) -> CommandResult:
        """Apply one of the four run signals (FR-016)."""
        run = await self._cmd.require_run(run_id)
        status = self._cmd.guard(run, signal.value, version)
        # Raises on an illegal signal, and on a terminal run says "never again"
        # rather than "not from here" (FR-013).
        apply_run_signal(status, signal)

        payload: dict[str, Any] = {} if reason is None else {"reason": reason}
        if signal is RunSignal.ABORT:
            # An abort must not leave a decision in front of the developer for
            # a run that has stopped: the approvals were neither decided nor
            # left to expire, so they are superseded (data-model).
            superseded = await self._approvals.supersede_pending(run_id, now=self._clock())
            if superseded:
                payload["superseded_approvals"] = len(superseded)

        result = await self._cmd.commit(
            run, [PendingEvent(event_type=_SIGNAL_EVENT[signal], payload=payload)], actor=actor
        )
        await self._audit_signal(result.run, signal, reason)
        return result

    async def _audit_signal(self, run: RunRow, signal: RunSignal, reason: str | None) -> None:
        """Audit the two moments FR-040 asks for by name.

        Pause and resume are not audited: the run's own log already carries
        them, and the audit trail exists for the coarse question "what did this
        vault do on its own" — a run that started and a run that ended.
        """
        if signal is RunSignal.START:
            event = AuditEventType.WORKFLOW_RUN_STARTED
        elif signal is RunSignal.ABORT:
            event = AuditEventType.WORKFLOW_RUN_FINISHED
        else:
            return
        await self._audit.record(
            event.value,
            actor="user",
            subject_kind="workflow_run",
            subject_name=run.id,
            detail={"status": run.status, "title": run.title, "reason": reason},
        )

    # -- restart ----------------------------------------------------------

    async def rebuild_projection(self, run_id: str) -> RunRow:
        """Rebuild a run from its events, and report what the restart lost.

        This is what the daemon calls at start (FR-014). Two things happen, in
        this order and not the other: an attempt left ``running`` by the
        process that died is failed with ``interrupted`` FIRST (FR-027), so the
        fold that follows already includes the ``node.failed`` that says so.
        The attempt keeps its ``conversation_id`` — the whole point of
        reporting an interruption rather than dropping it is that the
        conversation is still there to read.
        """
        run = await self._cmd.require_run(run_id)
        interrupted = await self._report_interrupted(run)

        projection = await self._cmd.fold(run_id)
        unchanged = (
            projection.status == run.status
            and projection.current_stage_key == run.current_stage_key
            and projection.current_node_key == run.current_node_key
            and projection.tokens_spent == run.tokens_spent
        )
        if unchanged and not interrupted:
            # Writing an identical projection would bump the version on every
            # daemon start, invalidating every client's observed version for a
            # change that is not one.
            return run
        rebuilt = await self._runs.update_run_projection(
            run_id, run.version, projection, now=self._clock()
        )
        if rebuilt is None:  # pragma: no cover - nothing else advances a run at boot
            return await self._cmd.require_run(run_id)
        return rebuilt

    async def _report_interrupted(self, run: RunRow) -> int:
        """Fail every attempt the dead process left mid-turn (FR-027)."""
        count = 0
        for attempt in await self._attempts.list_attempts(run.id):
            if attempt.status != NodeStatus.RUNNING.value:
                continue
            await self._attempts.update_attempt(
                attempt.id,
                status=NodeStatus.FAILED.value,
                failure_reason=FailureReason.INTERRUPTED.value,
                finished_at=self._clock(),
            )
            await self._cmd.append(
                run.id,
                PendingEvent(
                    event_type=EventType.NODE_FAILED,
                    stage_key=attempt.stage_key,
                    node_key=attempt.node_key,
                    payload={
                        "reason": FailureReason.INTERRUPTED.value,
                        "attempt": attempt.attempt,
                        "conversation_id": attempt.conversation_id,
                    },
                ),
                SYSTEM_ACTOR,
            )
            count += 1
        return count

    async def rebuild_all(self) -> int:
        """Rebuild every run this machine owns; answer how many moved."""
        rebuilt = 0
        for run in await self._runs.list_runs():
            if run.machine_id != self._cmd.machine_id:
                continue
            before = run.version
            after = await self.rebuild_projection(run.id)
            if after.version != before:
                rebuilt += 1
        return rebuilt

    # -- labels -----------------------------------------------------------

    async def relabel_run(
        self,
        run_id: str,
        *,
        title: str,
        description: str | KeepStored | None = KEEP,
    ) -> RunRow:
        """Rewrite what this run is CALLED and what it is for (FR-070).

        Delegates to ``run_label_ops`` to keep this module under the file-size
        limit; see that module for the full behaviour.
        """
        from coffer.application.workflow.run_label_ops import relabel_run as _relabel

        return await _relabel(self, run_id, title=title, description=description)

    # -- deletion ---------------------------------------------------------

    async def delete_run(self, run_id: str) -> None:
        """Delete the run, its log, its attempts, its approvals and its files.

        The row goes first: the four tables cascade from it, so a failure
        between the two steps leaves files with no run rather than a run with
        no files — an orphaned directory is recoverable by hand, a run pointing
        at a deleted tree is not. The node conversations are deliberately not
        touched; they are ordinary conversations under the chat layer's own
        retention (data-model, "Deletion").
        """
        run = await self._cmd.require_run(run_id)
        # FR-012: the run is visible here but only its owner may change it, and
        # deleting is the largest change there is.
        self._cmd.guard(run, "delete", None)
        await self._runs.delete_run(run_id)
        try:
            self._artifacts.delete_run_dir(run_id)
        except OSError:
            _logger.warning(
                "workflow.delete.run_dir_failed", extra={"run_id": run_id}, exc_info=True
            )
