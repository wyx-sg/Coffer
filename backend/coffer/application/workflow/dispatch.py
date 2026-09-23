"""The seam between "a node started" and "an agent is doing the work".

The node service owns run and node STATE; it never opens a conversation or
streams a turn. When a node becomes ``running`` it hands everything the work
needs to a :class:`NodeDispatcher` the composition root supplies — in
production ``node_driver``, in this layer's own tests a fake that records the
call and returns.

Why a callback rather than the node service calling ``TurnPlatformPort``
itself: the driver has to subscribe to the turn's event queue and report back
into the very service that started it, so a service that also drove the turn
would be its own caller. It also keeps the state machine testable without an
agent, which is what makes "a run advances, retries, loops and stops at its
ceiling" provable with no tokens spent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from coffer.application.workflow.ports import AttemptRow, RunRow
from coffer.domain.workflow.template import Node


@dataclass(frozen=True)
class NodeDispatch:
    """One unit of work for the driver: which node, on which attempt, where.

    ``node`` is a real :class:`Node` for both a template node and an ad-hoc
    task — an ad-hoc task is "recorded, contextualised and attributed exactly
    as a template node is" (spec workflow "Add an ad-hoc task to any stage"),
    so the driver is deliberately given no way to tell them apart beyond
    ``node.key``'s ``adhoc:`` prefix.

    ``follow_up`` is what makes feedback a message rather than a restart (spec
    workflow "Run a node's work as one conversation", "Accept the node actions
    start, feedback, complete, retry, skip and restore"): ``None`` opens the
    node's work, and a string is more to do on the attempt already in flight,
    whose conversation ``attempt`` names.
    """

    run: RunRow
    stage_key: str
    node: Node
    attempt: AttemptRow
    agent_key: str
    workdir: str
    #: What this attempt runs on (spec workflow "Choose a task's agent, model
    #: and effort before it starts"). ``None`` at either means the agent's own
    #: configuration decides, which is what it did before any of this.
    model: str | None = None
    effort: str | None = None
    follow_up: str | None = None

    @property
    def node_key(self) -> str:
        return self.node.key


class NodeDispatcher(Protocol):
    """What the advancer wires in so a node's turn actually happens.

    It returns nothing: the driver reports back through the node service's own
    ``record_output`` / ``record_failure``, so the result of a turn arrives as
    an event on the run's log like everything else rather than as a return
    value only the caller sees.
    """

    async def __call__(self, dispatch: NodeDispatch) -> None: ...
