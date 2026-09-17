"""The moves a node command is assembled from (spec workflow).

``node_service`` is the vocabulary — start, feedback, complete, retry, skip,
restore, report, task. This is the small set of moves each of those is made of:
settle a node, open its next attempt, ask whether the run is finished, hand the
work to the driver, and read the two things about a node that live in the event
log rather than in a column.

It exists as an object rather than a pile of free functions because all of them
need the same five collaborators, and threading five arguments through every
call would make each move's own argument list unreadable — which is the thing
that hides a missing guard.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import uuid4

from coffer.application.workflow.commands import (
    CommandResult,
    PendingEvent,
    RunCommands,
    template_of,
    utcnow,
)
from coffer.application.workflow.dispatch import NodeDispatch, NodeDispatcher
from coffer.application.workflow.kind import KIND_WORKFLOW
from coffer.application.workflow.node_walk import Walk, adhoc_node, walk_run
from coffer.application.workflow.ports import (
    ArtifactStorePort,
    AttemptRepoPort,
    AttemptRow,
    AuditPort,
    EventRepoPort,
    MachineIdPort,
    RunRepoPort,
    RunRow,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.error_base import CofferError
from coffer.domain.errors import ResourceNotFound
from coffer.domain.workflow.errors import IllegalTransition
from coffer.domain.workflow.events import EventActor, EventType
from coffer.domain.workflow.run import (
    ADHOC_KEY_PREFIX,
    FailureReason,
    NodeAction,
    NodeStatus,
)
from coffer.domain.workflow.template import Node, WorkflowTemplate
from coffer.domain.workflow.transitions import check_attempt_ceiling

#: A run is not a Resource, so an attempt is not either; ``ResourceNotFound`` is
#: reused for the same reason ``commands.KIND_RUN`` reuses it — every surface
#: already answers 404 to it.
KIND_ATTEMPT = "workflow_attempt"


class MissingRequiredArtifact(CofferError):  # noqa: N818
    """A node owing a required artifact has not produced it (FR-023).

    Its own error rather than an ``IllegalTransition``: the action WAS legal
    for the node's status, and the developer's next move is to write the file
    or waive it — not to pick a different action.
    """

    code = "WORKFLOW_MISSING_ARTIFACT"

    def __init__(self, node_key: str, missing: tuple[str, ...]) -> None:
        names = ", ".join(missing)
        super().__init__(
            f"node {node_key!r} owes {names}; write the artifact or complete it with "
            "waive_artifacts"
        )
        self.node_key = node_key
        self.missing = missing


class NodeOps:
    """The moves, over one set of collaborators."""

    def __init__(
        self,
        *,
        runs: RunRepoPort,
        events: EventRepoPort,
        attempts: AttemptRepoPort,
        artifacts: ArtifactStorePort,
        machine: MachineIdPort,
        audit: AuditPort,
        default_agent: str,
        dispatcher: NodeDispatcher | None = None,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.attempts = attempts
        self.artifacts = artifacts
        self.clock = clock
        self.cmd = RunCommands(
            runs=runs, events=events, attempts=attempts, machine=machine, clock=clock
        )
        self._audit = audit
        self._default_agent = default_agent
        self._dispatcher = dispatcher

    def set_dispatcher(self, dispatcher: NodeDispatcher) -> None:
        self._dispatcher = dispatcher

    # -- reading a node ----------------------------------------------------

    async def node_of(
        self, run: RunRow, template: WorkflowTemplate, node_key: str
    ) -> tuple[Node, str]:
        """The node a key names, whether the template declared it or the
        developer added it (FR-028), with the stage it sits in."""
        if node_key.startswith(ADHOC_KEY_PREFIX):
            return await self.adhoc_node_of(run.id, node_key)
        found = template.node(node_key)
        if found is None:
            raise IllegalTransition(
                f"run {run.id}",
                "no such node",
                node_key,
                tuple(node.key for _stage, node in template.ordered_nodes()),
            )
        stage, node = found
        return node, stage.key

    async def adhoc_node_of(self, run_id: str, node_key: str) -> tuple[Node, str]:
        """Rebuild an ad-hoc task's node from the event that added it.

        The event log is where it was recorded, so it is where it is read from
        — there is no second table holding a shadow copy to drift from it.
        """
        for row in await self.cmd.domain_events(run_id):
            if row.event_type is EventType.NODE_ADHOC_ADDED and row.node_key == node_key:
                return adhoc_node(node_key, row.payload), row.stage_key or ""
        raise IllegalTransition(f"run {run_id}", "no such task", node_key, ())

    async def attempt_row(self, attempt_id: str) -> AttemptRow:
        """One attempt by id.

        Read through ``update_attempt`` with nothing to change, which the port
        defines as leaving every field alone and returning the row: the
        repository has no get-by-id, and widening the port for a read this
        layer performs three times would be a wider seam than the need.
        """
        row = await self.attempts.update_attempt(attempt_id)
        if row is None:
            raise ResourceNotFound(KIND_ATTEMPT, attempt_id)
        return row

    async def require_attempt(self, run_id: str, node_key: str) -> AttemptRow:
        attempt = await self.attempts.latest_attempt(run_id, node_key)
        if attempt is None:
            raise IllegalTransition(
                f"node {node_key!r}", "not started", "report", (NodeAction.START.value,)
            )
        return attempt

    async def require_nothing_running(self, run_id: str, node_key: str) -> None:
        """At most one node of a run runs at any moment (FR-017)."""
        for key, row in (await self.cmd.latest_attempts(run_id)).items():
            if key != node_key and NodeStatus(row.status) is NodeStatus.RUNNING:
                raise IllegalTransition(f"run {run_id}", f"node {key} is running", "node.start", ())

    async def walk(self, run_id: str, *, just_settled: str | None = None) -> Walk:
        run = await self.cmd.require_run(run_id)
        return walk_run(
            template_of(run),
            await self.cmd.latest_attempts(run_id),
            just_settled=just_settled,
        )

    # -- moving a node -----------------------------------------------------

    async def attempt_for_action(
        self, run: RunRow, stage_key: str, node_key: str, action: NodeAction
    ) -> AttemptRow:
        """The attempt an action acts on, opening one when `skip` needs it.

        Every action but `start` needs a row to act on, and all but one of them
        genuinely require that the node was started. `skip` is the exception:
        the transition table says `pending` accepts it, and a stage that turns
        out not to apply is skipped before any work goes into it. So a skip
        with no attempt opens one and settles it in the same breath — without
        this the surface advertised a Skip that then answered 409.
        """
        attempt = await self.attempts.latest_attempt(run.id, node_key)
        if attempt is not None:
            return attempt
        if action is NodeAction.SKIP:
            return await self.open_attempt(run.id, stage_key, node_key, 1, None)
        raise IllegalTransition(
            f"node {node_key!r}", "not started", action.value, (NodeAction.START.value,)
        )

    async def settle(
        self,
        run: RunRow,
        template: WorkflowTemplate,
        node: Node,
        stage_key: str,
        attempt: AttemptRow,
        status: NodeStatus,
        event_type: EventType,
        payload: dict[str, Any],
        actor: EventActor,
    ) -> CommandResult:
        """Put a node into a terminal status, and close the run if it was last."""
        updated = await self.attempts.update_attempt(
            attempt.id, status=status.value, finished_at=self.clock()
        )
        events = [
            PendingEvent(
                event_type=event_type,
                stage_key=stage_key,
                node_key=node.key,
                payload={"attempt": attempt.attempt, **payload},
            )
        ]
        events.extend(await self.closing_events(run, template, node.key))
        result = await self.cmd.commit(run, events, actor=actor, attempt=updated or attempt)
        await self.audit_finished(result)
        return result

    async def reopen(
        self,
        run: RunRow,
        template: WorkflowTemplate,
        node: Node,
        stage_key: str,
        attempt: AttemptRow,
        event_type: EventType,
        payload: dict[str, Any],
        actor: EventActor,
        instructions: str | None = None,
    ) -> CommandResult:
        """Open the next attempt at a node; never rewrite the last one (FR-022).

        ``instructions`` overrides what the new attempt opens with. Left alone
        it carries the last attempt's brief forward, which is what a retry
        means: the same work, tried again.
        """
        number = check_attempt_ceiling(node.key, attempt.attempt, template.attempt_ceiling)
        opened = await self.open_attempt(
            run.id,
            stage_key,
            node.key,
            number,
            attempt.instructions if instructions is None else instructions,
        )
        return await self.cmd.commit(
            run,
            [
                PendingEvent(
                    event_type=event_type,
                    stage_key=stage_key,
                    node_key=node.key,
                    payload={"attempt": number, **payload},
                )
            ],
            actor=actor,
            attempt=opened,
        )

    async def open_attempt(
        self,
        run_id: str,
        stage_key: str,
        node_key: str,
        number: int,
        instructions: str | None = None,
    ) -> AttemptRow:
        return await self.attempts.insert_attempt(
            attempt_id=uuid4().hex,
            run_id=run_id,
            stage_key=stage_key,
            node_key=node_key,
            attempt=number,
            instructions=instructions,
        )

    async def closing_events(
        self, run: RunRow, template: WorkflowTemplate, just_settled: str
    ) -> list[PendingEvent]:
        """``run.completed`` when the node that just settled was the last one.

        Asked of the walk rather than of the template alone, so an ad-hoc task
        still pending holds the run open exactly as a template node would.
        """
        state = walk_run(
            template, await self.cmd.latest_attempts(run.id), just_settled=just_settled
        )
        if state.startable is None and not state.unfinished:
            return [PendingEvent(event_type=EventType.RUN_COMPLETED, payload={})]
        return []

    @staticmethod
    def run_failed(
        reason: FailureReason, stage_key: str | None, node_key: str, detail: object
    ) -> PendingEvent:
        """The event that ends a run with a reason rather than a loop (FR-026)."""
        return PendingEvent(
            event_type=EventType.RUN_FAILED,
            stage_key=stage_key,
            node_key=node_key,
            payload={"reason": reason.value, "node": node_key, "detail": str(detail)},
        )

    # -- handing the work over ---------------------------------------------

    async def dispatch(
        self,
        run: RunRow,
        stage_key: str,
        node: Node,
        attempt: AttemptRow,
        follow_up: str | None,
    ) -> None:
        """Hand the work to the driver, after the state is committed.

        After, not before: the driver reports back into the node service, and a
        report that arrived before the ``node.started`` event was written would
        be refused for acting on a node that had not started.
        """
        if self._dispatcher is None:
            return
        await self._dispatcher(
            NodeDispatch(
                run=run,
                stage_key=stage_key,
                node=node,
                attempt=attempt,
                agent_key=node.agent or await self.run_agent(run) or self._default_agent,
                workdir=await self.node_workdir(run, node.key),
                follow_up=follow_up,
            )
        )

    async def run_agent(self, run: RunRow) -> str | None:
        """The run's default agent, as ``run.created`` recorded it.

        There is no column for it: the run's own creation event is the record,
        which keeps the answer in the log with everything else about the run.
        """
        for row in await self.cmd.domain_events(run.id):
            if row.event_type is EventType.RUN_CREATED:
                return optional_str(row.payload.get("agent"))
        return None

    async def node_workdir(self, run: RunRow, node_key: str) -> str:
        """The run's working directory (FR-019), unless an ad-hoc task named
        another — which is how work in a second repository is expressed."""
        if not node_key.startswith(ADHOC_KEY_PREFIX):
            return run.workdir
        for row in await self.cmd.domain_events(run.id):
            if row.event_type is EventType.NODE_ADHOC_ADDED and row.node_key == node_key:
                return optional_str(row.payload.get("workdir")) or run.workdir
        return run.workdir

    async def audit_finished(self, result: CommandResult) -> None:
        """FR-040's coarse record: this vault finished a run it was running."""
        if not (result.appended(EventType.RUN_COMPLETED) or result.appended(EventType.RUN_FAILED)):
            return
        await self._audit.record(
            AuditEventType.WORKFLOW_RUN_FINISHED.value,
            actor="workflow",
            resource_kind=KIND_WORKFLOW,
            resource_name=result.run.id,
            detail={"status": result.run.status, "title": result.run.title},
        )


def optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None
