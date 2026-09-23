"""Choosing who runs a task, on what, before it runs (spec workflow
"Choose a task's agent, model and effort before it starts").

A task's agent came from the template and nothing else; its model and its
reasoning effort came from whatever the agent's own configuration projected.
The pickers that change those live on a CONVERSATION, and a task has no
conversation until it starts — so the one moment a developer most wants to say
"do this one on the bigger model", before it runs, was the one moment nothing
could be said.

The choice is recorded on the ATTEMPT rather than on the task, and that is the
point: a retry is a new attempt ("Keep every attempt when a node is retried"),
so picking a stronger model for the second try leaves the first attempt's row
still saying what it actually ran on. A run is a record of what happened, and
an override that rewrote history would make it a record of what was last
intended.

One ladder, three rungs, each deferring to the next rather than inventing a
default of its own: the attempt's own answer, then the template's, then the
agent's own configuration. ``None`` at any rung means "ask the next one", which
is why clearing an override is a real operation and not a magic string.

Only before it starts. Once the turn is in flight the agent owns the
conversation and the conversation owns these settings — the existing pickers on
the task's page write them there, which is the same place they would be written
for any other conversation. Two ways to set one thing that disagree about which
wins is worse than one way that stops being available.
"""

from __future__ import annotations

from coffer.application.workflow.commands import CommandResult, template_of
from coffer.application.workflow.node_ops import NodeOps
from coffer.domain.workflow.errors import IllegalTransition, UnknownWorkflowAgent
from coffer.domain.workflow.events import EventActor
from coffer.domain.workflow.run import NodeStatus

#: The one status that may be reassigned. Anything else has either started
#: (the conversation owns it) or finished (the record is what it ran on).
_ASSIGNABLE = NodeStatus.PENDING


async def assign(
    ops: NodeOps,
    run_id: str,
    node_key: str,
    *,
    agent: str | None,
    model: str | None,
    effort: str | None,
    actor: EventActor,
) -> CommandResult:
    """Record who is to run this task's next attempt, on what, at what effort.

    No optimistic lock and no event, for the same reason ``say`` has neither:
    this decides nothing about where the run is, and a choice addressed to a
    named task means the same thing wherever the run has got to.

    Opens the pending attempt if there is not one yet, exactly as briefing a
    task that the run has not reached does — the row is where the answer has to
    live, and a developer who has chosen an agent for a task has said something
    about it.

    Raises:
        IllegalTransition: the task has already started, so the conversation
            owns these settings now.
    """
    run = await ops.cmd.require_run(run_id)
    ops.cmd.guard(run, "node.assign", None)
    template = template_of(run)
    node, stage_key = await ops.node_of(run, template, node_key)

    # An empty string is not a choice, it is an empty box: read it as "defer",
    # the same as absent, rather than storing a value nothing can resolve.
    agent, model, effort = (agent or None), (model or None), (effort or None)
    known = ops.known_agents()
    if agent is not None and known and agent not in known:
        # Refused HERE rather than at the moment the task starts. Left to the
        # driver, a typed agent key becomes a failed attempt with an agent
        # error hours later, attributed to the work rather than to the choice.
        raise UnknownWorkflowAgent(agent, known)

    row = await ops.attempts.latest_attempt(run_id, node.key)
    if row is None:
        row = await ops.open_attempt(run.id, stage_key, node.key, 1)
    elif NodeStatus(row.status) is not _ASSIGNABLE:
        raise IllegalTransition(
            f"node {node_key!r}",
            row.status,
            "node.assign",
            (_ASSIGNABLE.value,),
        )

    updated = await ops.attempts.set_assignment(row.id, agent=agent, model=model, effort=effort)
    return CommandResult(run=run, events=(), attempt=updated or row)
