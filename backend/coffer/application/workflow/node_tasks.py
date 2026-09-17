"""Two commands that change the SHAPE of a run rather than a node's status.

A feedback edge sends the run backwards (FR-025, FR-026); an ad-hoc task adds
work the template never anticipated (FR-028). Both are ordinary commands — same
guard, same log, same projection — but neither is one of the six node actions,
and keeping them out of ``node_service``'s action dispatch is what stops the
surfaces from offering "skip" and "add a task" from the same enum.

They also end in the same place. Sending work back does not rewind the node
that passed: it adds a task to the earlier stage saying what is wrong, and that
task is an ad-hoc task like any other. So both commands below funnel into
``_add_task`` and the run has one way for unplanned work to exist, not two.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from coffer.application.workflow.commands import (
    CommandResult,
    PendingEvent,
    template_of,
)
from coffer.application.workflow.node_ops import NodeOps
from coffer.application.workflow.node_walk import adhoc_keys_named, adhoc_node_key
from coffer.application.workflow.ports import RunRow
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
    note: str | None = None,
    version: int,
    actor: EventActor,
) -> CommandResult:
    """Send the run back along a feedback edge (FR-025, FR-026).

    What arrives in the earlier stage is a new task named after the edge's
    reason, carrying ``note`` — what the developer found — as its brief. The
    node that already passed there is not reopened: its conversation was about
    a different problem, and the fix deserves its own.

    The ceiling counts this edge's own crossings, which it reads off the tasks
    the edge has already created (see ``adhoc_keys_named``). Reaching it fails
    the run with the reason rather than sending work back again.
    """
    run = await ops.cmd.require_run(run_id)
    ops.cmd.guard(run, "feedback_edge", version)
    template = template_of(run)
    taken = set(await ops.cmd.latest_attempts(run_id))
    try:
        outcome = take_feedback_edge(
            template,
            from_stage,
            reason,
            task_key=adhoc_node_key(reason, taken),
            firings_used=len(adhoc_keys_named(reason, taken)),
        )
    except AttemptCeilingReached as exc:
        # FR-026: the loop ends with the run failing and saying why, rather than
        # sending work back one more time.
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
    return await _add_task(
        ops,
        run,
        stage_key=outcome.target.stage_key,
        node_key=outcome.target.node_key,
        name=reason,
        instructions=(note or "").strip() or f"Sent back from {from_stage}: {reason}.",
        agent=None,
        workdir=None,
        actor=actor,
        extra={
            "cause": "feedback_edge",
            "reason": reason,
            "from_stage": from_stage,
            "firing": outcome.firing,
        },
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
    return await _add_task(
        ops,
        run,
        stage_key=stage_key,
        node_key=node_key,
        name=name,
        instructions=instructions,
        agent=agent,
        workdir=workdir,
        actor=actor,
    )


async def _add_task(
    ops: NodeOps,
    run: RunRow,
    *,
    stage_key: str,
    node_key: str,
    name: str,
    instructions: str,
    agent: str | None,
    workdir: str | None,
    actor: EventActor,
    extra: dict[str, Any] | None = None,
) -> CommandResult:
    """The attempt row and the event that make an ad-hoc task exist.

    ``extra`` is how a task says where it came from — a feedback edge records
    the edge it crossed there. Nothing reads it to decide anything; the task
    behaves identically either way, and that is the point.
    """
    row = await ops.attempts.insert_attempt(
        attempt_id=uuid4().hex,
        run_id=run.id,
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
                    **(extra or {}),
                },
            )
        ],
        actor=actor,
        attempt=row,
    )
