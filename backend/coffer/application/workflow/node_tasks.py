"""Two commands that change the SHAPE of a run rather than a node's status.

A feedback edge sends the run backwards (FR-025, FR-026); an ad-hoc task adds
work the template never anticipated (FR-028). Both are ordinary commands — same
guard, same log, same projection — but neither is one of the six node actions,
and keeping them out of ``node_service``'s action dispatch is what stops the
surfaces from offering "skip" and "add a task" from the same enum.
"""

from __future__ import annotations

from uuid import uuid4

from coffer.application.workflow.commands import (
    CommandResult,
    PendingEvent,
    template_of,
)
from coffer.application.workflow.node_ops import NodeOps
from coffer.application.workflow.node_walk import adhoc_node_key
from coffer.domain.workflow.errors import AttemptCeilingReached, IllegalTransition
from coffer.domain.workflow.events import EventActor, EventType
from coffer.domain.workflow.run import FailureReason
from coffer.domain.workflow.transitions import take_feedback_edge


async def take_feedback(
    ops: NodeOps,
    run_id: str,
    *,
    from_stage: str,
    reason: str,
    version: int,
    actor: EventActor,
) -> CommandResult:
    """Send the run back along a feedback edge (FR-025, FR-026)."""
    run = await ops.cmd.require_run(run_id)
    ops.cmd.guard(run, "feedback_edge", version)
    template = template_of(run)
    latest = await ops.cmd.latest_attempts(run_id)
    completed, _skipped = ops.cmd.settled_keys(latest)
    try:
        outcome = take_feedback_edge(
            template,
            from_stage,
            reason,
            completed_keys=completed,
            attempts=ops.cmd.attempts_used(latest),
        )
    except AttemptCeilingReached as exc:
        # FR-026: the loop ends with the run failing and saying why, rather than
        # opening the attempt that would spend the night.
        failed = await ops.cmd.commit(
            run,
            [ops.run_failed(FailureReason.ATTEMPT_CEILING, from_stage, exc.node_key, exc)],
            actor=actor,
        )
        # The run ended here as surely as it does on a completion, so it is
        # audited here too (FR-040) — a run that stopped because it hit a
        # ceiling is precisely the one the developer will come looking for.
        await ops.audit_finished(failed)
        return failed
    await ops.open_attempt(
        run_id, outcome.target.stage_key, outcome.target.node_key, outcome.attempt
    )
    # Only the target's attempt is opened: every node that completed in between
    # keeps its result, and the walk simply steps over them again on the way
    # forward (FR-025).
    return await ops.cmd.commit(
        run,
        [
            PendingEvent(
                event_type=EventType.NODE_RETRIED,
                stage_key=outcome.target.stage_key,
                node_key=outcome.target.node_key,
                payload={
                    "attempt": outcome.attempt,
                    "cause": "feedback_edge",
                    "reason": reason,
                    "from_stage": from_stage,
                    "reopened": list(outcome.reopened_keys),
                },
            )
        ],
        actor=actor,
    )


async def add_adhoc_task(
    ops: NodeOps,
    run_id: str,
    *,
    stage_key: str,
    name: str,
    instructions: str,
    version: int,
    agent: str | None,
    workdir: str | None,
    actor: EventActor,
) -> CommandResult:
    """Add unplanned work to a stage of a run (FR-028).

    It is recorded as a node with an ``adhoc:`` key, gets an attempt row like
    any node, and carries the developer's own instructions. Everything
    downstream — the context it opens with, where its artifacts land, how it is
    attributed, where the walk puts it — then treats it exactly as a template
    node, because by then it IS one.
    """
    run = await ops.cmd.require_run(run_id)
    ops.cmd.guard(run, "adhoc_task", version)
    template = template_of(run)
    if template.stage(stage_key) is None:
        raise IllegalTransition(
            f"run {run.id}", "adhoc", stage_key, tuple(s.key for s in template.stages)
        )
    node_key = adhoc_node_key(name, set(await ops.cmd.latest_attempts(run_id)))
    await ops.attempts.insert_attempt(
        attempt_id=uuid4().hex,
        run_id=run_id,
        stage_key=stage_key,
        node_key=node_key,
        attempt=1,
        instructions=instructions,
    )
    return await ops.cmd.commit(
        run,
        [
            PendingEvent(
                event_type=EventType.NODE_ADHOC_ADDED,
                stage_key=stage_key,
                node_key=node_key,
                payload={
                    "name": name,
                    "instructions": instructions,
                    "agent": agent,
                    "workdir": workdir,
                },
            )
        ],
        actor=actor,
    )
