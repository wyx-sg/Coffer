"""Adding work to a run that its workflow never anticipated (spec
workflow "Add an ad-hoc task to any stage").

An ad-hoc task is an ordinary command — same guard, same log, same projection —
but it is not one of the six node actions, and keeping it out of
``node_service``'s action dispatch is what stops the surfaces from offering
"skip" and "add a task" from the same enum.

It is also how a run goes backwards. There is no route in the template that
sends work to an earlier stage ("Send work back by the developer's hand, never
a template route"): a finding in a later task is acted on by retrying the task
that was wrong, or by adding a task here that fixes what was found. Nothing
that already ran is rewound either way, and the judgement about which of the
two to reach for belongs to whoever is holding the finding rather than to an
edge drawn before the run existed.
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
from coffer.application.workflow.node_walk import adhoc_node_key
from coffer.application.workflow.ports import RunRow
from coffer.domain.workflow.errors import IllegalTransition
from coffer.domain.workflow.events import EventActor, EventType
from coffer.domain.workflow.template import DEFAULT_ATTEMPT_CEILING


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
    """Add unplanned work to a stage of a run (spec workflow "Add an
    ad-hoc task to any stage").

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
    attempt_ceiling: int = DEFAULT_ATTEMPT_CEILING,
    extra: dict[str, Any] | None = None,
) -> CommandResult:
    """The attempt row and the event that make an ad-hoc task exist.

    ``extra`` is how a task says where it came from. Nothing reads it to decide
    anything; the task behaves identically either way, and that is the point.
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
                    # How many tries this task gets (spec workflow "Bound
                    # each task's attempts by its own ceiling"). Recorded
                    # HERE because an ad-hoc task exists nowhere else: the
                    # walk rebuilds it from this event, so a number left out
                    # is a number that silently becomes the default.
                    "attempt_ceiling": attempt_ceiling,
                    **(extra or {}),
                },
            )
        ],
        actor=actor,
        attempt=row,
    )
