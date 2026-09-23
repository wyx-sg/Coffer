"""Reading a workflow template out of the JSON a `resources` row holds.

A template has no table of its own (spec workflow "Register a template as a
workflow resource") — it is one ``resources`` row whose ``config`` holds the
whole definition. This module is the only place that config's shape is known:
:func:`parse_template` turns it into the frozen value objects of
``template_shape`` or refuses it naming the JSON path of the offending field
("Refuse an invalid template naming the offending path").

Every refusal names that path, which is the whole reason these rules are
hand-written rather than a schema: a caller told "invalid" learns nothing, and
a caller told ``stages[2].nodes[0].skill`` can fix it.

The shape itself is re-exported here, because every caller in the codebase
reaches for ``domain.workflow.template`` and a split that made them all change
import lines would be a refactor pretending to be a file-size fix.
"""

from __future__ import annotations

from collections.abc import Collection
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
    reject_unknown,
)
from coffer.domain.workflow.template_shape import (
    DEFAULT_ATTEMPT_CEILING,
    ApprovalPolicy,
    ArtifactSpec,
    FailureAction,
    Node,
    NodeType,
    OnFailure,
    Stage,
    WorkflowTemplate,
)

__all__ = [
    "DEFAULT_ATTEMPT_CEILING",
    "ApprovalPolicy",
    "ArtifactSpec",
    "FailureAction",
    "Node",
    "NodeType",
    "OnFailure",
    "Stage",
    "WorkflowTemplate",
    "parse_template",
]


def parse_template(
    config: Any,
    *,
    known_skills: Collection[str] | None = None,
    allowed_agents: Collection[str] | None = None,
) -> WorkflowTemplate:
    """Validate a template config and return its value objects, or refuse it.

    ``known_skills`` and ``allowed_agents`` are the two rules the domain cannot
    answer alone: whether a skill is registered, and whether an agent is inside
    the template's scope (spec workflow "Read a template's scope as the agents
    it may drive"). ``None`` means "not checked here" — the application passes
    the real collections at write time; a pure caller (a run replaying its own
    frozen snapshot) passes neither, because a snapshot was already validated
    once and re-refusing it would strand a run whose skill has since been
    renamed.

    Raises:
        TemplateInvalid: naming the JSON path of the offending field.
    """
    root = as_object(config, "")
    # ``edges`` is deliberately NOT accepted. A template that still carries one
    # is refused naming it, rather than having it dropped in silence: the route
    # it describes no longer exists (spec workflow "Send work back by the
    # developer's hand, never a template route"), and a workflow that still
    # thinks it has one would send work nowhere.
    reject_unknown(root, {"description", "stages"}, "")

    stages = _parse_stages(root, known_skills=known_skills, allowed_agents=allowed_agents)
    return WorkflowTemplate(
        stages=stages,
        description=as_optional_str(root.get("description"), "description"),
    )


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
                "model",
                "effort",
                "attempt_ceiling",
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
                model=as_optional_str(obj.get("model"), f"{path}.model"),
                effort=as_optional_str(obj.get("effort"), f"{path}.effort"),
                attempt_ceiling=as_attempt_ceiling(
                    obj.get("attempt_ceiling"),
                    f"{path}.attempt_ceiling",
                    default=DEFAULT_ATTEMPT_CEILING,
                ),
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
