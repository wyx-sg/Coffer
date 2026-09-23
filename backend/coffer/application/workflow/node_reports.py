"""What the driver reports back when a turn ends (spec workflow).

Two functions, and between them they decide almost everything about whether a
run advances on its own:

* :func:`record_output` — a turn produced something. A node whose approval
  policy is ``never``, which is not a manual step, and whose required artifacts
  are on disk completes right here, and the advancer moves to the next node
  with no command in between ("Run at most one node at a time"). Anything else
  stops at ``waiting_review``, which is where the developer finds it.
* :func:`record_failure` — a turn ended badly, and the node's own declared
  failure behaviour decides what the run does about it ("Handle a node
  failure as the node declares").

Free functions over :class:`NodeOps` rather than methods, for the file-size
ceiling and because they are genuinely one layer up from the moves they are
made of: each is a policy, and the policy is the part worth reading on its own.

Neither takes an observed version. The caller is the run's own machinery
reporting a turn it just ran, not a client acting on a view it read earlier, so
there is no observation to be stale about — see ``RunCommands.guard``.
"""

from __future__ import annotations

from coffer.application.workflow.commands import (
    ENGINE_ACTOR,
    CommandResult,
    PendingEvent,
    template_of,
)
from coffer.application.workflow.node_ops import NodeOps
from coffer.application.workflow.node_walk import artifact_gap
from coffer.application.workflow.ports import AttemptRow, RunRow
from coffer.domain.workflow.errors import AttemptCeilingReached, IllegalTransition
from coffer.domain.workflow.events import EventActor, EventType
from coffer.domain.workflow.run import FailureReason, NodeAction, NodeStatus
from coffer.domain.workflow.template import (
    ApprovalPolicy,
    FailureAction,
    Node,
    NodeType,
    WorkflowTemplate,
)
from coffer.domain.workflow.transitions import check_attempt_ceiling


async def record_output(
    ops: NodeOps,
    run_id: str,
    node_key: str,
    *,
    summary: str | None = None,
    tokens: int = 0,
    conversation_id: str | None = None,
    actor: EventActor = ENGINE_ACTOR,
) -> CommandResult:
    """A turn ended and left something behind."""
    run = await ops.cmd.require_run(run_id)
    ops.cmd.guard(run, "node.output_ready", None)
    template = template_of(run)
    node, stage_key = await ops.node_of(run, template, node_key)
    attempt = await ops.require_attempt(run_id, node_key)
    if NodeStatus(attempt.status) is not NodeStatus.RUNNING:
        raise IllegalTransition(
            f"node {node_key!r}", attempt.status, "output_ready", (NodeAction.RETRY.value,)
        )

    missing = artifact_gap(ops.artifacts, run_id, node, attempt.attempt)
    decides = _needs_the_developer(node, missing)
    events = [
        PendingEvent(
            event_type=EventType.NODE_OUTPUT_READY,
            stage_key=stage_key,
            node_key=node_key,
            payload={
                "attempt": attempt.attempt,
                "summary": summary,
                # The fold sums spend from this one payload field; carrying it
                # on the completion event as well would double the total.
                "tokens": max(tokens, 0),
                "missing_artifacts": list(missing),
            },
        )
    ]
    updated = await ops.attempts.update_attempt(
        attempt.id,
        status=(NodeStatus.WAITING_REVIEW if decides else NodeStatus.COMPLETED).value,
        summary=summary,
        conversation_id=conversation_id,
        tokens=tokens if tokens > 0 else None,
        finished_at=None if decides else ops.clock(),
    )
    if decides:
        return await ops.cmd.commit(run, events, actor=actor, attempt=updated or attempt)
    events.append(
        PendingEvent(
            event_type=EventType.NODE_COMPLETED,
            stage_key=stage_key,
            node_key=node_key,
            payload={"attempt": attempt.attempt},
        )
    )
    events.extend(await ops.closing_events(run, template, node_key))
    result = await ops.cmd.commit(run, events, actor=actor, attempt=updated or attempt)
    await ops.audit_finished(result)
    return result


def _needs_the_developer(node: Node, missing: tuple[str, ...]) -> bool:
    """Whether this output stops for a decision rather than completing.

    A manual node always does, however permissive its policy: its "output" is
    only the note telling the developer what to do, and the human step has not
    happened yet. A required artifact that was never written always does too —
    that is "Hold completion until a required artifact exists" arriving on the
    automatic path rather than the commanded one.
    """
    return node.approval is ApprovalPolicy.ALWAYS or node.type is NodeType.MANUAL or bool(missing)


async def record_failure(
    ops: NodeOps,
    run_id: str,
    node_key: str,
    *,
    reason: FailureReason = FailureReason.AGENT_ERROR,
    detail: str | None = None,
    actor: EventActor = ENGINE_ACTOR,
) -> CommandResult:
    """A turn ended badly; the node's declared behaviour decides (spec
    workflow "Handle a node failure as the node declares")."""
    run = await ops.cmd.require_run(run_id)
    ops.cmd.guard(run, "node.failed", None)
    template = template_of(run)
    node, stage_key = await ops.node_of(run, template, node_key)
    attempt = await ops.require_attempt(run_id, node_key)
    await ops.attempts.update_attempt(
        attempt.id,
        status=NodeStatus.FAILED.value,
        failure_reason=reason.value,
        finished_at=ops.clock(),
    )
    events = [
        PendingEvent(
            event_type=EventType.NODE_FAILED,
            stage_key=stage_key,
            node_key=node_key,
            payload={"attempt": attempt.attempt, "reason": reason.value, "detail": detail},
        )
    ]
    events.extend(await _after_failure(ops, run, template, node, stage_key, attempt))
    result = await ops.cmd.commit(run, events, actor=actor)
    await ops.audit_finished(result)
    return result


async def _after_failure(
    ops: NodeOps,
    run: RunRow,
    template: WorkflowTemplate,
    node: Node,
    stage_key: str,
    attempt: AttemptRow,
) -> list[PendingEvent]:
    """``stop``, ``continue`` or ``retry`` — the node said which (spec
    workflow "Handle a node failure as the node declares")."""
    behaviour = node.on_failure
    if behaviour.action is FailureAction.RETRY and attempt.attempt <= behaviour.times:
        try:
            # The node's own ``times`` is not a second ceiling: its
            # ``attempt_ceiling`` still caps it, so a task told to retry five
            # times but allowed three attempts stops at three (spec workflow
            # "Bound each task's attempts by its own ceiling").
            number = check_attempt_ceiling(node.key, attempt.attempt, node.attempt_ceiling)
        except AttemptCeilingReached as exc:
            return [ops.run_failed(FailureReason.ATTEMPT_CEILING, stage_key, node.key, exc)]
        await ops.open_attempt(run.id, stage_key, node.key, number, attempt.instructions)
        return [
            PendingEvent(
                event_type=EventType.NODE_RETRIED,
                stage_key=stage_key,
                node_key=node.key,
                payload={"attempt": number, "cause": "on_failure"},
            )
        ]
    if behaviour.action is FailureAction.CONTINUE:
        # The walk steps over a failed node whose template says to carry on, so
        # the run needs no event of its own here — but it may now be finished,
        # which is the same question a completion asks.
        return await ops.closing_events(run, template, node.key)
    return [
        PendingEvent(
            event_type=EventType.RUN_FAILED,
            stage_key=stage_key,
            node_key=node.key,
            payload={"reason": "node_failed", "node": node.key},
        )
    ]
