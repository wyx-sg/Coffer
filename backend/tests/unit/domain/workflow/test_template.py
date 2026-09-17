"""Template validation (spec workflow FR-002..FR-007).

Every refusal is checked for the JSON path it names, because that path is the
contract: a template is hand-written JSON and "invalid template" without a path
is a refusal the developer cannot act on.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from coffer.domain.workflow.errors import TemplateInvalid
from coffer.domain.workflow.template import (
    DEFAULT_ATTEMPT_CEILING,
    ApprovalPolicy,
    FailureAction,
    NodeType,
    parse_template,
)


def valid_config() -> dict[str, Any]:
    """The quickstart's three-stage template, which is a complete flow."""
    return {
        "description": "One repository, one change, design first",
        "attempt_ceiling": 3,
        "token_budget": 4_000_000,
        "stages": [
            {
                "key": "design",
                "name": "Tech Design",
                "optional": False,
                "nodes": [
                    {
                        "key": "draft_td",
                        "name": "Draft the technical design",
                        "type": "ai",
                        "skill": "coffer-writing-td",
                        "instructions": "Ground every identifier in this repository.",
                        "artifacts": [{"name": "td.md", "required": True}],
                        "approval": "never",
                        "on_failure": {"action": "retry", "times": 1},
                        "agent": None,
                    }
                ],
            },
            {
                "key": "coding",
                "name": "Coding",
                "nodes": [
                    {
                        "key": "implement",
                        "name": "Implement the change",
                        "type": "ai",
                        "artifacts": [{"name": "change-summary.md"}],
                    }
                ],
            },
            {
                "key": "testing",
                "name": "Testing",
                "nodes": [
                    {
                        "key": "verify",
                        "name": "Run the checks and report",
                        "type": "ai",
                    }
                ],
            },
        ],
        "edges": [{"from_stage": "testing", "to_stage": "coding", "reason": "code_issue"}],
    }


def _mutate(path: list[Any], value: Any, *, delete: bool = False) -> dict[str, Any]:
    """Return the valid config with one field replaced or removed."""
    config = valid_config()
    cursor: Any = config
    for step in path[:-1]:
        cursor = cursor[step]
    if delete:
        del cursor[path[-1]]
    else:
        cursor[path[-1]] = value
    return config


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="workflow", scenario="a template with any number of stages runs as written"
)
def test_a_valid_template_keeps_the_users_stages_in_their_order():
    template = parse_template(valid_config())
    assert [s.key for s in template.stages] == ["design", "coding", "testing"]
    assert [s.name for s in template.stages] == ["Tech Design", "Coding", "Testing"]


def test_nodes_are_reachable_by_key_alone_across_the_whole_template():
    template = parse_template(valid_config())
    found = template.node("verify")
    assert found is not None
    stage, node = found
    assert stage.key == "testing"
    assert node.name == "Run the checks and report"
    assert template.node("nothing_named_this") is None


def test_ordered_nodes_is_stages_in_order_then_nodes_within():
    template = parse_template(valid_config())
    assert [n.key for _, n in template.ordered_nodes()] == ["draft_td", "implement", "verify"]


def test_omitted_fields_take_the_documented_defaults():
    template = parse_template(
        {
            "stages": [
                {
                    "key": "only",
                    "name": "Only",
                    "nodes": [{"key": "n1", "name": "N1", "type": "manual"}],
                }
            ]
        }
    )
    node = template.stages[0].nodes[0]
    assert template.attempt_ceiling == DEFAULT_ATTEMPT_CEILING
    assert template.token_budget is None
    assert template.edges == ()
    assert template.stages[0].optional is False
    assert node.approval is ApprovalPolicy.NEVER
    assert node.on_failure.action is FailureAction.STOP
    assert node.on_failure.times == 0
    assert node.artifacts == ()
    assert node.skill is None and node.agent is None
    assert node.type is NodeType.MANUAL


def test_an_artifact_defaults_to_required():
    template = parse_template(valid_config())
    implement = template.node("implement")
    assert implement is not None
    assert implement[1].artifacts[0].required is True
    assert [a.name for a in implement[1].required_artifacts] == ["change-summary.md"]


def test_required_artifacts_excludes_the_optional_ones():
    config = _mutate(
        ["stages", 0, "nodes", 0, "artifacts"],
        [{"name": "td.md", "required": True}, {"name": "notes.md", "required": False}],
    )
    node = parse_template(config).stages[0].nodes[0]
    assert [a.name for a in node.artifacts] == ["td.md", "notes.md"]
    assert [a.name for a in node.required_artifacts] == ["td.md"]


def test_feedback_edges_are_parsed_with_their_reason():
    template = parse_template(valid_config())
    assert len(template.edges) == 1
    edge = template.edges[0]
    assert (edge.from_stage, edge.to_stage, edge.reason) == ("testing", "coding", "code_issue")


def test_stage_index_reports_template_order():
    template = parse_template(valid_config())
    assert template.stage_index("design") == 0
    assert template.stage_index("testing") == 2
    assert template.stage_index("absent") is None
    assert template.stage("coding") is not None
    assert template.stage("absent") is None


@pytest.mark.acceptance(
    spec="workflow", scenario="a template with any number of stages runs as written"
)
def test_the_engine_reads_no_meaning_from_a_key():
    """FR-003: a stage's meaning is its position; a non-English key is the same
    to the engine as `design`."""
    config = valid_config()
    config["stages"] = [config["stages"][0]]
    config["stages"][0]["key"] = "zhang-san-1"
    config["edges"] = []
    template = parse_template(config)
    assert template.stages[0].key == "zhang-san-1"
    assert template.stage_index("zhang-san-1") == 0


def test_a_registered_skill_and_an_in_scope_agent_pass():
    config = _mutate(["stages", 0, "nodes", 0, "agent"], "claude-code")
    template = parse_template(
        config,
        known_skills={"coffer-writing-td"},
        allowed_agents={"claude-code", "codex"},
    )
    assert template.stages[0].nodes[0].agent == "claude-code"


def test_omitting_the_collections_skips_the_two_checks_the_domain_cannot_answer():
    """A frozen snapshot re-parses without them: re-refusing a snapshot whose
    skill has since been renamed would strand a run that is already going."""
    config = _mutate(["stages", 0, "nodes", 0, "skill"], "a-skill-nobody-registered")
    template = parse_template(config)
    assert template.stages[0].nodes[0].skill == "a-skill-nobody-registered"


# --------------------------------------------------------------------------
# The refusals — one per rule, each asserting the offending path (FR-006)
# --------------------------------------------------------------------------

REFUSALS: list[tuple[str, dict[str, Any], str]] = [
    ("stages missing", {"description": "x"}, "stages"),
    ("stages empty", _mutate(["stages"], []), "stages"),
    ("stages not a list", _mutate(["stages"], {"design": {}}), "stages"),
    ("stage not an object", _mutate(["stages", 0], "design"), "stages[0]"),
    ("stage unknown field", _mutate(["stages", 0, "parallel"], True), "stages[0].parallel"),
    ("stage key missing", _mutate(["stages", 0, "key"], None, delete=True), "stages[0].key"),
    ("stage key empty", _mutate(["stages", 0, "key"], "  "), "stages[0].key"),
    ("stage key not a slug", _mutate(["stages", 0, "key"], "Design Stage"), "stages[0].key"),
    ("stage key leading dash", _mutate(["stages", 0, "key"], "-design"), "stages[0].key"),
    ("stage key too long", _mutate(["stages", 0, "key"], "a" * 65), "stages[0].key"),
    ("duplicate stage key", _mutate(["stages", 1, "key"], "design"), "stages[1].key"),
    ("stage name missing", _mutate(["stages", 0, "name"], None, delete=True), "stages[0].name"),
    ("stage name not a string", _mutate(["stages", 0, "name"], 7), "stages[0].name"),
    ("stage optional not a bool", _mutate(["stages", 0, "optional"], "yes"), "stages[0].optional"),
    ("nodes missing", _mutate(["stages", 1, "nodes"], None, delete=True), "stages[1].nodes"),
    ("nodes empty", _mutate(["stages", 1, "nodes"], []), "stages[1].nodes"),
    ("node not an object", _mutate(["stages", 0, "nodes", 0], "draft"), "stages[0].nodes[0]"),
    (
        "node unknown field",
        _mutate(["stages", 0, "nodes", 0, "artifact"], []),
        "stages[0].nodes[0].artifact",
    ),
    (
        "node key missing",
        _mutate(["stages", 0, "nodes", 0, "key"], None, delete=True),
        "stages[0].nodes[0].key",
    ),
    (
        "node key carries the adhoc separator",
        _mutate(["stages", 0, "nodes", 0, "key"], "adhoc:extra"),
        "stages[0].nodes[0].key",
    ),
    (
        "node key duplicated in another stage",
        _mutate(["stages", 2, "nodes", 0, "key"], "draft_td"),
        "stages[2].nodes[0].key",
    ),
    (
        "node name missing",
        _mutate(["stages", 0, "nodes", 0, "name"], None, delete=True),
        "stages[0].nodes[0].name",
    ),
    (
        "node type missing",
        _mutate(["stages", 0, "nodes", 0, "type"], None, delete=True),
        "stages[0].nodes[0].type",
    ),
    (
        "node type unknown",
        _mutate(["stages", 0, "nodes", 0, "type"], "review"),
        "stages[0].nodes[0].type",
    ),
    (
        "node instructions not a string",
        _mutate(["stages", 0, "nodes", 0, "instructions"], ["a"]),
        "stages[0].nodes[0].instructions",
    ),
    (
        "artifacts not a list",
        _mutate(["stages", 0, "nodes", 0, "artifacts"], {"name": "td.md"}),
        "stages[0].nodes[0].artifacts",
    ),
    (
        "artifact name with a separator",
        _mutate(["stages", 0, "nodes", 0, "artifacts"], [{"name": "docs/td.md"}]),
        "stages[0].nodes[0].artifacts[0].name",
    ),
    (
        "artifact name with a backslash",
        _mutate(["stages", 0, "nodes", 0, "artifacts"], [{"name": "docs\\td.md"}]),
        "stages[0].nodes[0].artifacts[0].name",
    ),
    (
        "artifact name dots only",
        _mutate(["stages", 0, "nodes", 0, "artifacts"], [{"name": ".."}]),
        "stages[0].nodes[0].artifacts[0].name",
    ),
    (
        "artifact name hidden",
        _mutate(["stages", 0, "nodes", 0, "artifacts"], [{"name": ".env"}]),
        "stages[0].nodes[0].artifacts[0].name",
    ),
    (
        "artifact name empty",
        _mutate(["stages", 0, "nodes", 0, "artifacts"], [{"name": ""}]),
        "stages[0].nodes[0].artifacts[0].name",
    ),
    (
        "duplicate artifact name",
        _mutate(["stages", 0, "nodes", 0, "artifacts"], [{"name": "td.md"}, {"name": "td.md"}]),
        "stages[0].nodes[0].artifacts[1].name",
    ),
    (
        "artifact required not a bool",
        _mutate(["stages", 0, "nodes", 0, "artifacts"], [{"name": "td.md", "required": "yes"}]),
        "stages[0].nodes[0].artifacts[0].required",
    ),
    (
        "artifact unknown field",
        _mutate(["stages", 0, "nodes", 0, "artifacts"], [{"name": "td.md", "optional": True}]),
        "stages[0].nodes[0].artifacts[0].optional",
    ),
    (
        "approval policy unknown",
        _mutate(["stages", 0, "nodes", 0, "approval"], "sometimes"),
        "stages[0].nodes[0].approval",
    ),
    (
        "on_failure not an object",
        _mutate(["stages", 0, "nodes", 0, "on_failure"], "retry"),
        "stages[0].nodes[0].on_failure",
    ),
    (
        "on_failure action unknown",
        _mutate(["stages", 0, "nodes", 0, "on_failure"], {"action": "explode"}),
        "stages[0].nodes[0].on_failure.action",
    ),
    (
        "on_failure retry with zero times",
        _mutate(["stages", 0, "nodes", 0, "on_failure"], {"action": "retry", "times": 0}),
        "stages[0].nodes[0].on_failure.times",
    ),
    (
        "on_failure times not an integer",
        _mutate(["stages", 0, "nodes", 0, "on_failure"], {"action": "retry", "times": "two"}),
        "stages[0].nodes[0].on_failure.times",
    ),
    (
        "on_failure unknown field",
        _mutate(["stages", 0, "nodes", 0, "on_failure"], {"action": "stop", "after": 1}),
        "stages[0].nodes[0].on_failure.after",
    ),
    ("attempt_ceiling zero", _mutate(["attempt_ceiling"], 0), "attempt_ceiling"),
    ("attempt_ceiling negative", _mutate(["attempt_ceiling"], -3), "attempt_ceiling"),
    ("attempt_ceiling not an integer", _mutate(["attempt_ceiling"], "3"), "attempt_ceiling"),
    ("attempt_ceiling a bool", _mutate(["attempt_ceiling"], True), "attempt_ceiling"),
    ("token_budget zero", _mutate(["token_budget"], 0), "token_budget"),
    ("token_budget not an integer", _mutate(["token_budget"], 1.5), "token_budget"),
    ("edges not a list", _mutate(["edges"], {"testing": "coding"}), "edges"),
    ("edge not an object", _mutate(["edges"], ["testing->coding"]), "edges[0]"),
    (
        "edge unknown field",
        _mutate(
            ["edges"],
            [{"from_stage": "testing", "to_stage": "coding", "reason": "r", "weight": 1}],
        ),
        "edges[0].weight",
    ),
    (
        "edge from an unknown stage",
        _mutate(["edges"], [{"from_stage": "release", "to_stage": "coding", "reason": "r"}]),
        "edges[0].from_stage",
    ),
    (
        "edge to an unknown stage",
        _mutate(["edges"], [{"from_stage": "testing", "to_stage": "release", "reason": "r"}]),
        "edges[0].to_stage",
    ),
    (
        "edge pointing forwards",
        _mutate(["edges"], [{"from_stage": "design", "to_stage": "testing", "reason": "r"}]),
        "edges[0].to_stage",
    ),
    (
        "edge pointing at its own stage",
        _mutate(["edges"], [{"from_stage": "coding", "to_stage": "coding", "reason": "r"}]),
        "edges[0].to_stage",
    ),
    (
        "edge without a reason",
        _mutate(["edges"], [{"from_stage": "testing", "to_stage": "coding"}]),
        "edges[0].reason",
    ),
    ("root unknown field", _mutate(["retries"], 2), "retries"),
]


@pytest.mark.parametrize(
    ("config", "path"),
    [pytest.param(config, path, id=case_id) for case_id, config, path in REFUSALS],
)
@pytest.mark.acceptance(
    spec="workflow", scenario="an invalid template is refused with the offending path"
)
def test_an_invalid_template_is_refused_naming_the_offending_path(
    config: dict[str, Any], path: str
):
    with pytest.raises(TemplateInvalid) as caught:
        parse_template(config)
    assert caught.value.path == path
    # The path is in the message too — a surface that logs only str(exc) still
    # tells the developer where to look.
    assert path in str(caught.value)


def test_a_non_object_config_is_refused_at_the_root():
    with pytest.raises(TemplateInvalid) as caught:
        parse_template(["stages"])
    assert caught.value.path == "<root>"


@pytest.mark.acceptance(
    spec="workflow", scenario="an invalid template is refused with the offending path"
)
def test_an_unregistered_skill_is_refused_with_its_node_path():
    with pytest.raises(TemplateInvalid) as caught:
        parse_template(valid_config(), known_skills={"some-other-skill"})
    assert caught.value.path == "stages[0].nodes[0].skill"
    assert "coffer-writing-td" in str(caught.value)


@pytest.mark.acceptance(
    spec="workflow", scenario="an invalid template is refused with the offending path"
)
def test_an_agent_outside_the_templates_scope_is_refused():  # FR-007
    config = _mutate(["stages", 1, "nodes", 0, "agent"], "codex")
    with pytest.raises(TemplateInvalid) as caught:
        parse_template(config, allowed_agents={"claude-code"})
    assert caught.value.path == "stages[1].nodes[0].agent"


@pytest.mark.acceptance(
    spec="workflow", scenario="an invalid template is refused with the offending path"
)
def test_nothing_is_kept_from_a_refused_template():
    """The refusal carries the reason, not a half-parsed template — there is no
    partially-valid template object to leak into a caller."""
    config = _mutate(["stages", 1, "key"], "design")
    before = copy.deepcopy(config)
    with pytest.raises(TemplateInvalid):
        parse_template(config)
    assert config == before
