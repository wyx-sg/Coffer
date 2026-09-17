"""Talking to a task — at any point in its life (FR-068).

A run is driven by TALKING (FR-063), and the composer on a task's page is
therefore the whole interface. What one sentence MEANS depends on where the
task is, and this module is the one place that decides:

* **Not started yet** — the sentence is queued onto the attempt the task will
  open with, and arrives in its brief (FR-029). This is how a developer says
  "when you get to the migration, use the 0088 style" before the run reaches it.
* **Waiting for review** — the turn has ended and the task is the developer's
  again, so the sentence reopens that same turn with more to do. Not a new
  attempt: it is the same piece of work, carrying on (FR-021, FR-022).
* **Finished** — completed, skipped or failed — the sentence opens the NEXT
  attempt with itself as the brief, bounded by the template's ceiling. A task
  the developer is still talking to is not finished, whatever its row says.

Two statuses refuse, and both for the same reason: something else owns the
task. While a turn is RUNNING the agent owns it, and the sentence belongs in
the conversation, which queues it server-side — the surface sends it there
directly and never through here. While an approval is pending the DECISION owns
it, and answering an approval in prose is exactly what the gate exists to
prevent (FR-039).
"""

from __future__ import annotations

from coffer.application.workflow.commands import CommandResult, PendingEvent, template_of
from coffer.application.workflow.node_ops import NodeOps
from coffer.application.workflow.ports import AttemptRow, RunRow
from coffer.domain.workflow.errors import IllegalTransition
from coffer.domain.workflow.events import EventActor, EventType
from coffer.domain.workflow.run import NodeAction, NodeStatus
from coffer.domain.workflow.template import Node

#: The statuses that refuse a sentence, and what owns the task instead.
_OWNED_BY = {
    NodeStatus.RUNNING: "its turn",
    NodeStatus.WAITING_APPROVAL: "its approval",
}


async def say(
    ops: NodeOps,
    run_id: str,
    node_key: str,
    *,
    text: str,
    actor: EventActor,
) -> CommandResult:
    """Say something to one task, whatever state it is in (FR-068).

    No optimistic lock: the version exists so a decision made against an
    observed state is not applied to a different one (FR-015), and a sentence
    addressed to a named task means the same thing wherever the run has got to.
    A composer that refused text because the run advanced while it was being
    typed would be a worse engine, not a safer one. The run's other two guards
    still apply — another machine's run and a finished run refuse this as they
    refuse everything (FR-012, FR-013).
    """
    words = text.strip()
    if not words:
        raise IllegalTransition(f"node {node_key!r}", "nothing said", "say", ())
    run = await ops.cmd.require_run(run_id)
    ops.cmd.guard(run, "node.say", None)
    template = template_of(run)
    node, stage_key = await ops.node_of(run, template, node_key)
    attempt = await ops.attempts.latest_attempt(run_id, node_key)

    if attempt is None:
        # Nothing has opened yet, so the brief needs a row to live on. It is
        # pending, which is what a task with no attempt row already was.
        opened = await ops.open_attempt(run.id, stage_key, node.key, 1, words)
        return await _briefed(ops, run, stage_key, node, opened, words, actor)

    status = NodeStatus(attempt.status)
    owner = _OWNED_BY.get(status)
    if owner is not None:
        raise IllegalTransition(f"node {node.key!r} belongs to {owner}", status.value, "say", ())
    if status is NodeStatus.PENDING:
        briefed = await ops.attempts.update_attempt(
            attempt.id, instructions=_joined(attempt.instructions, words)
        )
        return await _briefed(ops, run, stage_key, node, briefed or attempt, words, actor)
    if status is NodeStatus.WAITING_REVIEW:
        return await feedback(ops, run, node, stage_key, attempt, words, actor)
    # Completed, skipped or failed: the next attempt opens with what was said.
    return await ops.reopen(
        run,
        template,
        node,
        stage_key,
        attempt,
        EventType.NODE_RETRIED,
        {"cause": "said", "said": words},
        actor,
        instructions=_joined(attempt.instructions, words),
    )


async def feedback(
    ops: NodeOps,
    run: RunRow,
    node: Node,
    stage_key: str,
    attempt: AttemptRow,
    text: str,
    actor: EventActor,
) -> CommandResult:
    """More to do on the attempt already open — not a new try (FR-021)."""
    if not text.strip():
        raise IllegalTransition(
            f"node {node.key!r}", attempt.status, "feedback", (NodeAction.COMPLETE.value,)
        )
    running = await ops.attempts.update_attempt(attempt.id, status=NodeStatus.RUNNING.value)
    result = await ops.cmd.commit(
        run,
        [
            PendingEvent(
                event_type=EventType.NODE_FEEDBACK_SUBMITTED,
                stage_key=stage_key,
                node_key=node.key,
                payload={"attempt": attempt.attempt, "feedback": text},
            )
        ],
        actor=actor,
        attempt=running or attempt,
    )
    await ops.dispatch(result.run, stage_key, node, running or attempt, text)
    return result


async def _briefed(
    ops: NodeOps,
    run: RunRow,
    stage_key: str,
    node: Node,
    attempt: AttemptRow,
    words: str,
    actor: EventActor,
) -> CommandResult:
    """Record that a task not yet running was told something.

    ``node.briefed`` and not ``node.feedback_submitted``, because the latter
    moves the run's position to the node it names — and saying what a LATER
    task should do must not make the run claim to be there.
    """
    return await ops.cmd.commit(
        run,
        [
            PendingEvent(
                event_type=EventType.NODE_BRIEFED,
                stage_key=stage_key,
                node_key=node.key,
                payload={"attempt": attempt.attempt, "said": words},
            )
        ],
        actor=actor,
        attempt=attempt,
    )


def _joined(existing: str | None, words: str) -> str:
    """What was already there, then what was just said.

    Appended rather than replaced: an ad-hoc task's brief and a second thought
    about it are both things the developer wrote, and dropping the first would
    make the second a correction they never asked for.
    """
    before = (existing or "").strip()
    return f"{before}\n\n{words}" if before else words
