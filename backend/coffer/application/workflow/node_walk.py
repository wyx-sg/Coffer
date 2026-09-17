"""Where a run stands, and the two questions only the application can answer.

``domain.workflow.transitions.next_node`` walks the TEMPLATE. That is the whole
rule for a run with nothing but template nodes, and it is deliberately blind to
two things the domain has no way to see:

* an **ad-hoc task** (FR-028) is not in the template at all — it is an attempt
  row in a stage, and it holds its stage open exactly as a template node does;
* a **failed** node is neither completed nor skipped, so the template walk hands
  it back forever. Whether the run steps over it is its ``on_failure``
  behaviour's answer (FR-024), not the walk's.

So the walk that the advancer and the run-completion check both use lives here,
over the attempt rows, and both use *this one* — a second implementation would
eventually disagree with the first about a node the template said to continue
past, and a run would either stall or finish twice.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

from coffer.application.workflow.ports import ArtifactStorePort, AttemptRow
from coffer.domain.workflow.run import ADHOC_KEY_PREFIX, NodeStatus
from coffer.domain.workflow.template import ApprovalPolicy, Node, NodeType, WorkflowTemplate
from coffer.domain.workflow.transitions import NodePosition

#: Statuses in which a node has finished having things happen to it. A failed
#: node is settled too: whether the run steps over it or stops on it is its
#: ``on_failure`` behaviour's answer (FR-024), taken when it failed, not the
#: walk's to re-decide every time it is asked.
_SETTLED: frozenset[NodeStatus] = frozenset(
    {NodeStatus.COMPLETED, NodeStatus.SKIPPED, NodeStatus.FAILED}
)

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
#: The ``-2``, ``-3`` a repeated name gets, as ``adhoc_node_key`` spells it.
_SUFFIXED = re.compile(r"-\d+")


@dataclass(frozen=True)
class Walk:
    """The answer to "what now".

    ``startable`` is the node the advancer may dispatch — ``None`` both when
    everything is done and when a node is already holding the run, which is why
    ``unfinished`` is reported beside it: the two together tell "the run is
    finished" apart from "the run is busy", and completion needs that
    distinction to be right (FR-013).
    """

    startable: NodePosition | None
    unfinished: tuple[str, ...]
    occupied_by: str | None = None


def walk_run(
    template: WorkflowTemplate,
    latest: Mapping[str, AttemptRow],
    *,
    just_settled: str | None = None,
) -> Walk:
    """Walk stages in order; within a stage, template nodes then its ad-hoc tasks.

    The rule is one sentence: **the first node that is not settled is where the
    run is**. If it is pending it may start; if it is running, in review or at
    an approval, nothing else may start behind it — which is FR-017 and, just as
    importantly, the reason a node awaiting the developer's review is never
    overtaken by the node after it.

    Ordering first-unsettled rather than "is anything open anywhere" is also
    what makes a feedback edge work (FR-025): the edge adds its task to a stage
    EARLIER in the order, and the walk hands that task straight back even though
    the node the edge was taken from is still sitting in review. When the fix is
    done the walk returns to that node, because it never stopped being open.

    An ad-hoc task runs at the END of the stage it was added to: the stage's own
    plan was written first, and a task that joined later has no claim to come
    before the work already declared.

    ``just_settled`` names a node whose new terminal status the caller has
    written to its attempt row but not necessarily read back; it is treated as
    settled so a completion check made inside the same command sees the node it
    just settled.
    """
    open_keys: list[tuple[str, str, NodeStatus | None]] = []
    for stage in template.stages:
        keys = [node.key for node in stage.nodes]
        keys.extend(adhoc_keys_in(latest, stage.key))
        for key in keys:
            status = _status_of(latest.get(key), key, just_settled)
            if status is None or status not in _SETTLED:
                open_keys.append((stage.key, key, status))

    if not open_keys:
        return Walk(startable=None, unfinished=())
    stage_key, node_key, status = open_keys[0]
    unfinished = tuple(key for _stage, key, _status in open_keys)
    if status is None or status is NodeStatus.PENDING:
        return Walk(
            startable=NodePosition(stage_key=stage_key, node_key=node_key),
            unfinished=unfinished,
        )
    return Walk(startable=None, unfinished=unfinished, occupied_by=node_key)


def _status_of(row: AttemptRow | None, key: str, just_settled: str | None) -> NodeStatus | None:
    if key == just_settled:
        # Settled by the command that is asking; whichever terminal status it
        # landed in, it is not open any more.
        return NodeStatus.COMPLETED
    if row is None:
        return None
    return NodeStatus(row.status)


def adhoc_keys_in(latest: Mapping[str, AttemptRow], stage_key: str) -> list[str]:
    """The ad-hoc tasks added to one stage, in the order they were added.

    Sorted by key rather than by a timestamp: the key carries a numeric suffix
    when a name repeats, and an attempt row's ``started_at`` is null until the
    task runs — which is exactly when the order matters.
    """
    return sorted(
        key
        for key, row in latest.items()
        if key.startswith(ADHOC_KEY_PREFIX) and row.stage_key == stage_key
    )


def adhoc_node(node_key: str, payload: Mapping[str, Any]) -> Node:
    """An ad-hoc task as a :class:`Node`, from the event that recorded it.

    Typed ``ai`` and policy ``never``: the developer wrote the instructions
    themselves and is watching the run they added it to, so putting their own
    task behind their own approval would ask them the same question twice. Its
    external writes are gated at the gateway like every other node's.
    """
    name = payload.get("name")
    agent = payload.get("agent")
    instructions = payload.get("instructions")
    return Node(
        key=node_key,
        name=name if isinstance(name, str) and name else node_key,
        type=NodeType.AI,
        instructions=instructions if isinstance(instructions, str) else None,
        approval=ApprovalPolicy.NEVER,
        agent=agent if isinstance(agent, str) and agent else None,
    )


def adhoc_slug(name: str) -> str:
    """The slug half of an ad-hoc key: narrowed to what a path segment and an
    event identifier both accept, and never empty."""
    return _SLUG_STRIP.sub("-", name.strip().lower()).strip("-")[:48] or "task"


def adhoc_node_key(name: str, taken: Collection[str]) -> str:
    """``adhoc:<slug>``, unique within the run (FR-028).

    A node key is a path segment on disk and an identifier in every event, so
    the slug is narrowed to what both accept and a repeat of the same name gets
    a numeric suffix rather than silently sharing another task's attempts.
    """
    base = adhoc_slug(name)
    candidate = f"{ADHOC_KEY_PREFIX}{base}"
    suffix = 2
    while candidate in taken:
        candidate = f"{ADHOC_KEY_PREFIX}{base}-{suffix}"
        suffix += 1
    return candidate


def adhoc_keys_named(name: str, taken: Collection[str]) -> tuple[str, ...]:
    """Every key ``adhoc_node_key(name, ...)`` has already minted for ``name``.

    This is how a feedback edge counts its own crossings (FR-026): the edge
    names the tasks it creates after itself, so the tasks bearing that name ARE
    the firings, and no counter has to be stored and kept honest across a
    restart.

    It counts by name, so a task the developer added by hand under the same
    name is counted too. That is the direction to be wrong in: the count comes
    out high, the edge stops sooner, and the failure mode is a loop that ends
    early rather than one that never ends.
    """
    base = f"{ADHOC_KEY_PREFIX}{adhoc_slug(name)}"
    return tuple(
        sorted(key for key in taken if key == base or _SUFFIXED.fullmatch(key[len(base) :]))
    )


def artifact_gap(
    store: ArtifactStorePort, run_id: str, node: Node, attempt: int
) -> tuple[str, ...]:
    """The required artifacts this attempt owes and has not written (FR-023).

    Read from the directory, never from a list something maintained: the
    catalogue is generated from what is on disk (FR-031), and completion has to
    answer to the same source or the two would disagree about what exists.
    """
    required = {spec.name for spec in node.required_artifacts}
    if not required:
        return ()
    present = {
        entry.name
        for entry in store.list_artifacts(run_id)
        if entry.node_key == node.key and entry.attempt == attempt
    }
    return tuple(sorted(required - present))
