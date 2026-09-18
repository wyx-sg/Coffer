"""Handing a task's work to the driver, and answering what it runs on.

Split out of ``NodeOps`` to keep that module under its line ceiling. The seam
is real rather than arithmetic: everything else there decides whether something
may happen and writes the row that says it did, while these three answer
questions ABOUT a task that is already going to run — who runs it, on what, and
in which directory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.application.workflow.dispatch import NodeDispatch
from coffer.application.workflow.ports import AttemptRow, RunRow
from coffer.domain.workflow.events import EventType
from coffer.domain.workflow.run import ADHOC_KEY_PREFIX
from coffer.domain.workflow.template import Node

if TYPE_CHECKING:  # pragma: no cover - a cycle at runtime, types only
    from coffer.application.workflow.node_ops import NodeOps


def optional_str(value: object) -> str | None:
    """A payload field that is a non-empty string, or nothing at all."""
    return value if isinstance(value, str) and value else None


async def dispatch(
    ops: NodeOps,
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
    if ops._dispatcher is None:
        return
    await ops._dispatcher(
        NodeDispatch(
            run=run,
            stage_key=stage_key,
            node=node,
            attempt=attempt,
            # One ladder (FR-071): this attempt's own answer, then the
            # task's, then the run's, then this machine's default. Each
            # rung defers to the next rather than inventing a default.
            agent_key=(
                attempt.agent or node.agent or await run_agent(ops, run) or ops._default_agent
            ),
            model=attempt.model or node.model,
            effort=attempt.effort or node.effort,
            workdir=await node_workdir(ops, run, node.key),
            follow_up=follow_up,
        )
    )


async def run_agent(ops: NodeOps, run: RunRow) -> str | None:
    """The run's default agent, as ``run.created`` recorded it.

    There is no column for it: the run's own creation event is the record,
    which keeps the answer in the log with everything else about the run.
    """
    for row in await ops.cmd.domain_events(run.id):
        if row.event_type is EventType.RUN_CREATED:
            return optional_str(row.payload.get("agent"))
    return None


async def node_workdir(ops: NodeOps, run: RunRow, node_key: str) -> str:
    """The run's working directory (FR-019), unless an ad-hoc task named
    another — which is how work in a second repository is expressed."""
    if not node_key.startswith(ADHOC_KEY_PREFIX):
        return run.workdir
    for row in await ops.cmd.domain_events(run.id):
        if row.event_type is EventType.NODE_ADHOC_ADDED and row.node_key == node_key:
            return optional_str(row.payload.get("workdir")) or run.workdir
    return run.workdir
