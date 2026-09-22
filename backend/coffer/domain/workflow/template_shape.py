"""The SHAPE of a workflow: the value objects the engine executes.

Split from ``template``, which reads this shape out of JSON. They change for
different reasons — a new field on a task is one line here and a paragraph of
validation there — and keeping them apart stops the file that says what a
workflow IS from being mostly about what a malformed one is.

Everything here is frozen. A run freezes its template at creation (FR-010), and
a value object that could be edited afterwards would make that freeze a
promise the type system did not keep.

The engine reads no meaning from any key (FR-003). ``design``, ``coding`` and
``张三的阶段`` are the same to it — a stage's meaning is its position and
nothing else, which is why nothing here special-cases a name.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

#: Default when a template does not state one. A ceiling is mandatory (FR-026),
#: so the absence of the field is a default rather than "no ceiling".
DEFAULT_ATTEMPT_CEILING = 3

#: What a task that declared no deliverable is given (FR-072). A task's
#: artifacts are the only thing it says to the tasks after it — those open with
#: an index of what the run produced, not with anybody's conversation — so a
#: task owing nothing is a task whose work leaves the run when its conversation
#: closes. Supplied where the template is READ rather than written into the
#: developer's stored template, so a task they later give a deliverable of its
#: own does not end up owing two.
DEFAULT_ARTIFACT_NAME = "report.md"


class NodeType(StrEnum):
    """Who does the work.

    TWO values, because the engine only ever asked one question of this field:
    does a turn get dispatched, or does the run stop and wait for a person?
    ``manual`` records a human step and never opens a conversation, which is
    why it is a type rather than a flag on the node.

    It was four. ``coding`` and ``notification`` sat beside ``ai`` and did
    exactly what ``ai`` did — the engine branched on ``manual`` and nothing
    else — so they described what the work was ABOUT rather than who did it,
    which is what the node's name and its instructions are for.

    A third value is reserved in spirit and absent in fact: a step that runs a
    fixed program rather than an agent. When Coffer can run one, it gets a
    value here; until then, a value claiming a deterministic executor that the
    engine would quietly hand to an agent would be a lie in the data model.
    """

    AI = "ai"
    MANUAL = "manual"


class ApprovalPolicy(StrEnum):
    """Whether the node's own action needs the developer's say-so (FR-033).

    Two values, not a scale: the write-class gate on tool calls is a separate
    mechanism, and a third policy here would only duplicate it badly.
    """

    NEVER = "never"
    ALWAYS = "always"


class FailureAction(StrEnum):
    """What the run does when this node fails (FR-024)."""

    STOP = "stop"
    CONTINUE = "continue"
    RETRY = "retry"


@dataclass(frozen=True)
class OnFailure:
    """A node's declared failure behaviour. ``times`` is meaningful only for
    ``retry``, where it is the number of extra attempts this node's own failure
    handling may open — the run-wide attempt ceiling still caps it."""

    action: FailureAction = FailureAction.STOP
    times: int = 0


@dataclass(frozen=True)
class ArtifactSpec:
    """A deliverable a node owes. ``name`` is a single path segment because it
    becomes a file under the run's artifact directory and nothing else."""

    name: str
    required: bool = True


@dataclass(frozen=True)
class Node:
    """One step: what to do, with which skill, on which agent, owing what.

    ``attempt_ceiling`` is this task's own limit and nobody else's (FR-026).
    It used to be one number for the whole template, which made the drafting
    task that is cheap to re-run and the deploy task that must not be tried
    twice share a cap that was wrong for one of them.
    """

    key: str
    name: str
    type: NodeType
    skill: str | None = None
    instructions: str | None = None
    artifacts: tuple[ArtifactSpec, ...] = ()
    approval: ApprovalPolicy = ApprovalPolicy.NEVER
    on_failure: OnFailure = OnFailure()
    agent: str | None = None
    #: What this task runs on when nobody has overridden it (FR-071). ``None``
    #: defers to the agent's own configuration — the same ladder an attempt's
    #: own override sits one rung above.
    model: str | None = None
    effort: str | None = None
    attempt_ceiling: int = DEFAULT_ATTEMPT_CEILING

    @property
    def required_artifacts(self) -> tuple[ArtifactSpec, ...]:
        """The artifacts whose absence blocks completion (FR-023).

        Read off ``owed_artifacts``, not off ``artifacts``: the deliverable a
        task was given because it declared none (FR-072) is required like any
        other, or the default would be a line in a brief that nothing checks.
        """
        return tuple(a for a in self.owed_artifacts if a.required)

    @property
    def owed_artifacts(self) -> tuple[ArtifactSpec, ...]:
        """What this task owes, never empty (FR-072).

        Read this rather than ``artifacts`` wherever the answer drives
        behaviour — the brief a task opens with, and whether it may complete.
        ``artifacts`` stays the developer's own declaration so that editing the
        template round-trips what they wrote.
        """
        return self.artifacts or (ArtifactSpec(name=DEFAULT_ARTIFACT_NAME, required=True),)


@dataclass(frozen=True)
class Stage:
    """An ordered group of nodes, named by the user."""

    key: str
    name: str
    nodes: tuple[Node, ...]
    optional: bool = False


@dataclass(frozen=True)
class WorkflowTemplate:
    """The whole shape of the work. Frozen at run creation (FR-010).

    Stages in the order they run, and that is the whole of the order. There is
    no route back: a finding in a later task is acted on by retrying the task
    that was wrong or by adding one that fixes it (FR-025), because whether a
    failing test means redo the code or redo the design is a judgement only
    whoever is holding the finding can make — an edge drawn when the template
    was written makes it in advance, and for every run alike.
    """

    stages: tuple[Stage, ...]
    description: str | None = None

    def stage(self, key: str) -> Stage | None:
        return next((s for s in self.stages if s.key == key), None)

    def stage_index(self, key: str) -> int | None:
        for index, stage in enumerate(self.stages):
            if stage.key == key:
                return index
        return None

    def node(self, key: str) -> tuple[Stage, Node] | None:
        """The stage and node a key names, or ``None``. Keys are unique across
        the whole template, so one key needs no stage to disambiguate it."""
        for stage in self.stages:
            for node in stage.nodes:
                if node.key == key:
                    return stage, node
        return None

    def ordered_nodes(self) -> tuple[tuple[Stage, Node], ...]:
        """Every node in execution order — stages in order, nodes within."""
        return tuple((stage, node) for stage in self.stages for node in stage.nodes)
