"""The workflow template: value objects and the validation rules (spec workflow).

A template has no table of its own (FR-001) — it is one ``resources`` row whose
``config`` holds the whole definition. This module is the only place that
config's shape is known: :func:`parse_template` turns it into frozen value
objects or refuses it naming the JSON path of the offending field (FR-006).

The engine reads no meaning from any key (FR-003). ``design``, ``coding`` and
``张三的阶段`` are the same to it — a stage's meaning is its position and
nothing else, which is why nothing below special-cases a name.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from coffer.domain.workflow.errors import TemplateInvalid
from coffer.domain.workflow.template_fields import (
    as_artifact_name,
    as_attempt_ceiling,
    as_bool,
    as_enum,
    as_int,
    as_key,
    as_object,
    as_optional_str,
    as_required_str,
    as_token_budget,
    reject_unknown,
)

#: Default when a template does not state one. A ceiling is mandatory (FR-026),
#: so the absence of the field is a default rather than "no ceiling".
DEFAULT_ATTEMPT_CEILING = 3


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
    """One step: what to do, with which skill, on which agent, owing what."""

    key: str
    name: str
    type: NodeType
    skill: str | None = None
    instructions: str | None = None
    artifacts: tuple[ArtifactSpec, ...] = ()
    approval: ApprovalPolicy = ApprovalPolicy.NEVER
    on_failure: OnFailure = OnFailure()
    agent: str | None = None

    @property
    def required_artifacts(self) -> tuple[ArtifactSpec, ...]:
        """The artifacts whose absence blocks completion (FR-023)."""
        return tuple(a for a in self.artifacts if a.required)


@dataclass(frozen=True)
class Stage:
    """An ordered group of nodes, named by the user."""

    key: str
    name: str
    nodes: tuple[Node, ...]
    optional: bool = False


@dataclass(frozen=True)
class FeedbackEdge:
    """An edge from a later stage back to an earlier one, with the reason that
    takes it (FR-005). A forward edge is the default order and is not written,
    so every edge here is strictly backwards."""

    from_stage: str
    to_stage: str
    reason: str


@dataclass(frozen=True)
class WorkflowTemplate:
    """The whole shape of the work. Frozen at run creation (FR-010)."""

    stages: tuple[Stage, ...]
    edges: tuple[FeedbackEdge, ...] = ()
    description: str | None = None
    attempt_ceiling: int = DEFAULT_ATTEMPT_CEILING
    token_budget: int | None = None

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


def parse_template(
    config: Any,
    *,
    known_skills: Collection[str] | None = None,
    allowed_agents: Collection[str] | None = None,
) -> WorkflowTemplate:
    """Validate a template config and return its value objects, or refuse it.

    ``known_skills`` and ``allowed_agents`` are the two rules the domain cannot
    answer alone: whether a skill is registered, and whether an agent is inside
    the template's scope (FR-007). ``None`` means "not checked here" — the
    application passes the real collections at write time; a pure caller
    (a run replaying its own frozen snapshot) passes neither, because a
    snapshot was already validated once and re-refusing it would strand a run
    whose skill has since been renamed.

    Raises:
        TemplateInvalid: naming the JSON path of the offending field.
    """
    root = as_object(config, "")
    reject_unknown(root, {"description", "attempt_ceiling", "token_budget", "stages", "edges"}, "")

    stages = _parse_stages(root, known_skills=known_skills, allowed_agents=allowed_agents)
    template = WorkflowTemplate(
        stages=stages,
        edges=_parse_edges(root.get("edges"), stages),
        description=as_optional_str(root.get("description"), "description"),
        attempt_ceiling=as_attempt_ceiling(
            root.get("attempt_ceiling"), default=DEFAULT_ATTEMPT_CEILING
        ),
        token_budget=as_token_budget(root.get("token_budget")),
    )
    return template


def _parse_stages(
    root: dict[str, Any],
    *,
    known_skills: Collection[str] | None,
    allowed_agents: Collection[str] | None,
) -> tuple[Stage, ...]:
    raw_stages = root.get("stages")
    if not isinstance(raw_stages, list) or not raw_stages:
        raise TemplateInvalid("stages", "at least one stage is required")

    stages: list[Stage] = []
    seen_stage_keys: set[str] = set()
    # Node keys are unique across the WHOLE template, not merely within a
    # stage, because an event names a node by key alone — two stages each with
    # a `review` node would make every `node.completed` event ambiguous.
    seen_node_keys: dict[str, str] = {}

    for i, raw in enumerate(raw_stages):
        path = f"stages[{i}]"
        stage_obj = as_object(raw, path)
        reject_unknown(stage_obj, {"key", "name", "optional", "nodes"}, path)
        key = as_key(stage_obj.get("key"), f"{path}.key")
        if key in seen_stage_keys:
            raise TemplateInvalid(f"{path}.key", f"duplicate stage key {key!r}")
        seen_stage_keys.add(key)

        nodes = _parse_nodes(
            stage_obj.get("nodes"),
            path,
            seen_node_keys,
            known_skills=known_skills,
            allowed_agents=allowed_agents,
        )
        stages.append(
            Stage(
                key=key,
                name=as_required_str(stage_obj.get("name"), f"{path}.name"),
                nodes=nodes,
                optional=as_bool(stage_obj.get("optional"), f"{path}.optional", default=False),
            )
        )
    return tuple(stages)


def _parse_nodes(
    raw_nodes: Any,
    stage_path: str,
    seen_node_keys: dict[str, str],
    *,
    known_skills: Collection[str] | None,
    allowed_agents: Collection[str] | None,
) -> tuple[Node, ...]:
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise TemplateInvalid(f"{stage_path}.nodes", "at least one node is required")

    nodes: list[Node] = []
    for j, raw in enumerate(raw_nodes):
        path = f"{stage_path}.nodes[{j}]"
        obj = as_object(raw, path)
        reject_unknown(
            obj,
            {
                "key",
                "name",
                "type",
                "skill",
                "instructions",
                "artifacts",
                "approval",
                "on_failure",
                "agent",
            },
            path,
        )
        key = as_key(obj.get("key"), f"{path}.key")
        if key in seen_node_keys:
            raise TemplateInvalid(
                f"{path}.key",
                f"duplicate node key {key!r}; it is already used by {seen_node_keys[key]}",
            )
        seen_node_keys[key] = path

        skill = as_optional_str(obj.get("skill"), f"{path}.skill")
        if skill is not None and known_skills is not None and skill not in known_skills:
            raise TemplateInvalid(f"{path}.skill", f"no registered skill named {skill!r}")
        agent = as_optional_str(obj.get("agent"), f"{path}.agent")
        if agent is not None and allowed_agents is not None and agent not in allowed_agents:
            raise TemplateInvalid(
                f"{path}.agent",
                f"agent {agent!r} is outside this template's scope",
            )

        nodes.append(
            Node(
                key=key,
                name=as_required_str(obj.get("name"), f"{path}.name"),
                type=as_enum(NodeType, obj.get("type"), f"{path}.type"),
                skill=skill,
                instructions=as_optional_str(obj.get("instructions"), f"{path}.instructions"),
                artifacts=_parse_artifacts(obj.get("artifacts"), path),
                approval=as_enum(
                    ApprovalPolicy,
                    obj.get("approval"),
                    f"{path}.approval",
                    default=ApprovalPolicy.NEVER,
                ),
                on_failure=_parse_on_failure(obj.get("on_failure"), path),
                agent=agent,
            )
        )
    return tuple(nodes)


def _parse_artifacts(raw: Any, node_path: str) -> tuple[ArtifactSpec, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise TemplateInvalid(f"{node_path}.artifacts", "must be a list")
    specs: list[ArtifactSpec] = []
    seen: set[str] = set()
    for k, item in enumerate(raw):
        path = f"{node_path}.artifacts[{k}]"
        obj = as_object(item, path)
        reject_unknown(obj, {"name", "required"}, path)
        name = as_artifact_name(obj.get("name"), f"{path}.name")
        if name in seen:
            raise TemplateInvalid(f"{path}.name", f"duplicate artifact name {name!r}")
        seen.add(name)
        specs.append(
            ArtifactSpec(
                name=name,
                required=as_bool(obj.get("required"), f"{path}.required", default=True),
            )
        )
    return tuple(specs)


def _parse_on_failure(raw: Any, node_path: str) -> OnFailure:
    path = f"{node_path}.on_failure"
    if raw is None:
        return OnFailure()
    obj = as_object(raw, path)
    reject_unknown(obj, {"action", "times"}, path)
    action = as_enum(FailureAction, obj.get("action"), f"{path}.action", default=FailureAction.STOP)
    raw_times = obj.get("times")
    if action is not FailureAction.RETRY:
        # `times` answers a question only `retry` asks; carrying a number for
        # `stop` would read as a promise the engine never keeps.
        return OnFailure(action=action, times=0)
    times = 1 if raw_times is None else as_int(raw_times, f"{path}.times")
    if times < 1:
        raise TemplateInvalid(f"{path}.times", "must be >= 1 when the action is retry")
    return OnFailure(action=action, times=times)


def _parse_edges(raw: Any, stages: tuple[Stage, ...]) -> tuple[FeedbackEdge, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise TemplateInvalid("edges", "must be a list")
    order = {stage.key: index for index, stage in enumerate(stages)}
    edges: list[FeedbackEdge] = []
    for i, item in enumerate(raw):
        path = f"edges[{i}]"
        obj = as_object(item, path)
        reject_unknown(obj, {"from_stage", "to_stage", "reason"}, path)
        from_stage = as_required_str(obj.get("from_stage"), f"{path}.from_stage")
        to_stage = as_required_str(obj.get("to_stage"), f"{path}.to_stage")
        if from_stage not in order:
            raise TemplateInvalid(f"{path}.from_stage", f"no stage named {from_stage!r}")
        if to_stage not in order:
            raise TemplateInvalid(f"{path}.to_stage", f"no stage named {to_stage!r}")
        # A forward edge is the default order and is never written, so one here
        # is a mistake rather than a shortcut — and a self-edge would be a loop
        # with no progress between its ends.
        if order[to_stage] >= order[from_stage]:
            raise TemplateInvalid(
                f"{path}.to_stage",
                f"{to_stage!r} must come strictly before {from_stage!r}",
            )
        edges.append(
            FeedbackEdge(
                from_stage=from_stage,
                to_stage=to_stage,
                reason=as_required_str(obj.get("reason"), f"{path}.reason"),
            )
        )
    return tuple(edges)
