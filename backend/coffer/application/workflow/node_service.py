"""``WorkflowNodeService`` — the commands that act on one node (spec workflow).

The six node actions (FR-021), the feedback edge (FR-025, FR-026), the ad-hoc
task (FR-028), and the reports the driver makes back when a turn ends.

This service owns node STATE and nothing else. It never opens a conversation:
when a node becomes ``running`` it hands a ``NodeDispatch`` to the dispatcher
the composition root wired in, and the driver on the other side reports the
result back through :meth:`record_output` or :meth:`record_failure`. Keeping
the turn on the other side of that seam is what lets the whole state machine —
advance, retry, loop, stop at the ceiling — be proved with no agent, no network
and no tokens.

The node walk lives in ``node_walk`` rather than in the advancer for the same
reason: "which node may start now" is one answer, and two implementations of it
would eventually disagree about a failed node the template says to continue
past — one stalling the run and the other finishing it twice.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from coffer.application.workflow import node_reports, node_say, node_tasks
from coffer.application.workflow.commands import (
    DEFAULT_ACTOR,
    ENGINE_ACTOR,
    CommandResult,
    PendingEvent,
    template_of,
    utcnow,
)
from coffer.application.workflow.dispatch import NodeDispatcher
from coffer.application.workflow.kind import KIND_WORKFLOW
from coffer.application.workflow.node_ops import MissingRequiredArtifact, NodeOps
from coffer.application.workflow.node_walk import Walk, artifact_gap
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
from coffer.domain.workflow.errors import IllegalTransition
from coffer.domain.workflow.events import EventActor, EventType
from coffer.domain.workflow.run import FailureReason, NodeAction, NodeStatus, RunStatus
from coffer.domain.workflow.template import Node, WorkflowTemplate
from coffer.domain.workflow.transitions import NodePosition, apply_node_action

__all__ = ["KIND_WORKFLOW", "MissingRequiredArtifact", "WorkflowNodeService"]


class WorkflowNodeService:
    """Commands that act on one node of a run."""

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
        self._ops = NodeOps(
            runs=runs,
            events=events,
            attempts=attempts,
            artifacts=artifacts,
            machine=machine,
            audit=audit,
            default_agent=default_agent,
            dispatcher=dispatcher,
            clock=clock,
        )

    def bind_dispatcher(self, dispatcher: NodeDispatcher) -> None:
        """Wire the driver in after construction.

        The driver reports back into this service, so one of the two has to be
        built first; this keeps that cycle out of the composition root rather
        than out of the design.
        """
        self._ops.set_dispatcher(dispatcher)

    # -- the six actions --------------------------------------------------

    async def act(
        self,
        run_id: str,
        node_key: str,
        action: NodeAction,
        *,
        version: int,
        feedback: str | None = None,
        waive_artifacts: bool = False,
        actor: EventActor = DEFAULT_ACTOR,
    ) -> CommandResult:
        """One entry point for the six node actions (FR-021)."""
        ops = self._ops
        run = await ops.cmd.require_run(run_id)
        ops.cmd.guard(run, f"node.{action.value}", version)
        template = template_of(run)
        node, stage_key = await ops.node_of(run, template, node_key)
        if action is NodeAction.START:
            started = await ops.attempts.latest_attempt(run_id, node_key)
            return await self._start(run, template, node, stage_key, started, actor)
        attempt = await ops.attempt_for_action(run, stage_key, node_key, action)
        # Raises when the action is not legal here, and says what is instead —
        # the domain's table is the only place that answer lives.
        apply_node_action(NodeStatus(attempt.status), action, node.type)

        if action is NodeAction.FEEDBACK:
            return await node_say.feedback(
                ops, run, node, stage_key, attempt, feedback or "", actor
            )
        if action is NodeAction.COMPLETE:
            return await self._complete(
                run, template, node, stage_key, attempt, waive_artifacts, actor
            )
        if action is NodeAction.SKIP:
            return await ops.settle(
                run,
                template,
                node,
                stage_key,
                attempt,
                NodeStatus.SKIPPED,
                EventType.NODE_SKIPPED,
                {},
                actor,
            )
        # `retry` and `restore` both open the NEXT attempt and leave the last
        # one as it is (FR-022); the event type is their whole difference, so a
        # restored node still shows that the developer had skipped it.
        event_type = (
            EventType.NODE_RETRIED if action is NodeAction.RETRY else EventType.NODE_RESTORED
        )
        return await ops.reopen(run, template, node, stage_key, attempt, event_type, {}, actor)

    async def _start(
        self,
        run: RunRow,
        template: WorkflowTemplate,
        node: Node,
        stage_key: str,
        attempt: AttemptRow | None,
        actor: EventActor,
    ) -> CommandResult:
        """Open (or take up) an attempt and hand it to the driver."""
        ops = self._ops
        if RunStatus(run.status) is not RunStatus.RUNNING:
            raise IllegalTransition(
                f"run {run.id}", run.status, "node.start", (RunStatus.RUNNING.value,)
            )
        if ops.cmd.budget_exceeded(template, run):
            # FR-018: reaching the budget pauses the run instead of starting the
            # next node. Its own event type so the reason survives; an ordinary
            # pause once folded.
            return await ops.cmd.commit(
                run,
                [
                    PendingEvent(
                        event_type=EventType.RUN_BUDGET_EXCEEDED,
                        stage_key=stage_key,
                        node_key=node.key,
                        payload={
                            "token_budget": template.token_budget,
                            "tokens_spent": run.tokens_spent,
                        },
                    )
                ],
                actor=actor,
            )
        await ops.require_nothing_running(run.id, node.key)

        if attempt is None:
            attempt = await ops.open_attempt(run.id, stage_key, node.key, 1)
        apply_node_action(NodeStatus(attempt.status), NodeAction.START, node.type)
        started = await ops.attempts.update_attempt(
            attempt.id, status=NodeStatus.RUNNING.value, started_at=ops.clock()
        )
        result = await ops.cmd.commit(
            run,
            [
                PendingEvent(
                    event_type=EventType.NODE_STARTED,
                    stage_key=stage_key,
                    node_key=node.key,
                    payload={"attempt": attempt.attempt, "type": node.type.value},
                )
            ],
            actor=actor,
            attempt=started or attempt,
        )
        # A manual node is dispatched like any other: the driver is the one
        # place that knows a ``manual`` node opens no conversation, and routing
        # it around the driver would put that rule in two places. What keeps it
        # honest is ``node_reports``, where a manual node always stops for the
        # developer rather than completing on its own.
        await ops.dispatch(result.run, stage_key, node, started or attempt, None)
        return result

    async def _complete(
        self,
        run: RunRow,
        template: WorkflowTemplate,
        node: Node,
        stage_key: str,
        attempt: AttemptRow,
        waive_artifacts: bool,
        actor: EventActor,
    ) -> CommandResult:
        """Complete the node, and the run with it when nothing is left."""
        ops = self._ops
        missing = artifact_gap(ops.artifacts, run.id, node, attempt.attempt)
        if missing and not waive_artifacts:
            # FR-023: the node waits for the developer to supply the file or
            # waive it. Refusing the command IS that wait — the node keeps the
            # status it had, and nothing about the run moves.
            raise MissingRequiredArtifact(node.key, missing)
        payload: dict[str, Any] = {}
        if missing:
            payload["waived_artifacts"] = list(missing)
        return await ops.settle(
            run,
            template,
            node,
            stage_key,
            attempt,
            NodeStatus.COMPLETED,
            EventType.NODE_COMPLETED,
            payload,
            actor,
        )

    # -- what the driver reports back -------------------------------------

    async def record_output(
        self,
        run_id: str,
        node_key: str,
        *,
        summary: str | None = None,
        tokens: int = 0,
        conversation_id: str | None = None,
        actor: EventActor = ENGINE_ACTOR,
    ) -> CommandResult:
        """A turn ended and left something behind (FR-017)."""
        return await node_reports.record_output(
            self._ops,
            run_id,
            node_key,
            summary=summary,
            tokens=tokens,
            conversation_id=conversation_id,
            actor=actor,
        )

    async def record_failure(
        self,
        run_id: str,
        node_key: str,
        *,
        reason: FailureReason = FailureReason.AGENT_ERROR,
        detail: str | None = None,
        actor: EventActor = ENGINE_ACTOR,
    ) -> CommandResult:
        """A turn ended badly; the node's declared behaviour decides (FR-024)."""
        return await node_reports.record_failure(
            self._ops, run_id, node_key, reason=reason, detail=detail, actor=actor
        )

    # -- the same reports, keyed the way the driver holds them -------------
    #
    # The driver knows an attempt by its id and nothing else, so these three are
    # the translation — the composition root wires it with bound methods rather
    # than a closure keeping its own attempt table.

    async def record_conversation(self, attempt_id: str, conversation_id: str) -> None:
        """Put the conversation on the attempt before its turn starts.

        No event and no version bump: it is not a state change, it is the
        attempt acquiring the thing that makes an interruption readable. The
        driver calls it before the first turn precisely so a process that dies
        mid-turn leaves a row that still names the conversation (FR-027).
        """
        await self._ops.attempts.update_attempt(attempt_id, conversation_id=conversation_id)

    async def report_output(self, attempt_id: str, summary: str, tokens: int = 0) -> CommandResult:
        row = await self._ops.attempt_row(attempt_id)
        return await self.record_output(row.run_id, row.node_key, summary=summary, tokens=tokens)

    async def report_failure(
        self,
        attempt_id: str,
        reason: FailureReason = FailureReason.AGENT_ERROR,
        detail: str | None = None,
    ) -> CommandResult:
        row = await self._ops.attempt_row(attempt_id)
        return await self.record_failure(row.run_id, row.node_key, reason=reason, detail=detail)

    async def say(
        self,
        run_id: str,
        node_key: str,
        *,
        text: str,
        actor: EventActor = DEFAULT_ACTOR,
    ) -> CommandResult:
        """Say something to one task, whatever state it is in (FR-068)."""
        return await node_say.say(self._ops, run_id, node_key, text=text, actor=actor)

    # -- feedback edges and ad-hoc work -----------------------------------

    async def take_feedback(
        self,
        run_id: str,
        *,
        from_stage: str,
        reason: str,
        note: str | None = None,
        version: int,
        actor: EventActor = DEFAULT_ACTOR,
    ) -> CommandResult:
        """Send the run back along a feedback edge (FR-025, FR-026)."""
        return await node_tasks.take_feedback(
            self._ops,
            run_id,
            from_stage=from_stage,
            reason=reason,
            note=note,
            version=version,
            actor=actor,
        )

    async def add_adhoc_task(
        self,
        run_id: str,
        *,
        stage_key: str,
        name: str,
        instructions: str,
        version: int,
        agent: str | None = None,
        workdir: str | None = None,
        actor: EventActor = DEFAULT_ACTOR,
    ) -> CommandResult:
        """Add unplanned work to a stage of a run (FR-028)."""
        return await node_tasks.add_adhoc_task(
            self._ops,
            run_id,
            stage_key=stage_key,
            name=name,
            instructions=instructions,
            version=version,
            agent=agent,
            workdir=workdir,
            actor=actor,
        )

    # -- what the advancer asks -------------------------------------------

    async def walk(self, run_id: str) -> Walk:
        """Where the run stands: what may start, and what is still open."""
        return await self._ops.walk(run_id)

    async def next_position(self, run_id: str) -> NodePosition | None:
        """The node the advancer should start now, or ``None``."""
        return (await self.walk(run_id)).startable
