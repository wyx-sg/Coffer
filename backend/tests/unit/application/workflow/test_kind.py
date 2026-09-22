"""The ``workflow`` Kind: what it declares, and what it refuses at write time.

The refusal is the point. A template is hand-written JSON that later runs
unattended, so the moment to catch a typo is the write — and the refusal is only
useful if it names the field (FR-006).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from coffer.application.workflow.kind import (
    KIND_WORKFLOW,
    WorkflowTemplateConfig,
    make_workflow_kind,
    validate_template_agents,
)

from .conftest import TEMPLATE


@pytest.mark.acceptance(spec="workflow", scenario="a template is registered as a resource")
def test_the_kind_declares_what_the_framework_needs() -> None:
    kind = make_workflow_kind()

    assert kind.name == KIND_WORKFLOW
    assert kind.display_name == "Workflow"
    assert kind.config_schema is WorkflowTemplateConfig
    # A template has no directory behind it, so the generic create path makes a
    # complete resource.
    assert kind.generic_create_allowed is True
    # Its scope is read inverted — the agents it may drive (FR-007).
    assert kind.supports_scope is True
    # A flow defined here must be available on the developer's other machines
    # (FR-008).
    assert kind.converges is True
    # Deleting a template cannot strand a run, which froze its snapshot.
    assert kind.on_delete is None


def test_a_valid_template_round_trips_unchanged() -> None:
    validated = WorkflowTemplateConfig.model_validate(TEMPLATE)

    assert validated.model_dump(mode="json") == TEMPLATE


@pytest.mark.parametrize(
    ("config", "path"),
    [
        ({"stages": []}, "stages"),
        ({"stages": [{"key": "Design", "name": "D", "nodes": []}]}, "stages[0].key"),
        (
            {"stages": [{"key": "d", "name": "D", "nodes": [{"key": "n", "name": "N"}]}]},
            "stages[0].nodes[0].type",
        ),
        (
            {
                "stages": [
                    {
                        "key": "d",
                        "name": "D",
                        "nodes": [
                            {
                                "key": "n",
                                "name": "N",
                                "type": "ai",
                                "artifacts": [{"name": "a/b.md"}],
                            }
                        ],
                    }
                ]
            },
            "stages[0].nodes[0].artifacts[0].name",
        ),
        # A template carrying a route between stages, which is what an editor
        # written against the old shape would still send (FR-025).
        (
            {
                "stages": [
                    {"key": "a", "name": "A", "nodes": [{"key": "x", "name": "X", "type": "ai"}]},
                    {"key": "b", "name": "B", "nodes": [{"key": "y", "name": "Y", "type": "ai"}]},
                ],
                "edges": [{"from_stage": "b", "to_stage": "a", "reason": "r"}],
            },
            "edges",
        ),
    ],
)
@pytest.mark.acceptance(
    spec="workflow", scenario="an invalid template is refused with the offending path"
)
def test_an_invalid_template_is_refused_naming_the_field(
    config: dict[str, object], path: str
) -> None:
    with pytest.raises(ValidationError) as caught:
        WorkflowTemplateConfig.model_validate(config)

    assert path in str(caught.value)


def test_a_node_naming_an_unregistered_skill_is_refused() -> None:
    kind = make_workflow_kind(known_skills=["coffer-writing-td"])
    config = {
        "stages": [
            {
                "key": "d",
                "name": "D",
                "nodes": [{"key": "n", "name": "N", "type": "ai", "skill": "no-such-skill"}],
            }
        ]
    }

    assert kind.validate_config is not None
    with pytest.raises(ValueError, match=r"stages\[0\]\.nodes\[0\]\.skill"):
        kind.validate_config(config)


def test_a_node_naming_an_agent_outside_the_scope_is_refused() -> None:
    """FR-007: the scope says which agents this template may drive."""
    config = {
        "stages": [
            {
                "key": "d",
                "name": "D",
                "nodes": [{"key": "n", "name": "N", "type": "ai", "agent": "codex"}],
            }
        ]
    }

    with pytest.raises(ValueError, match=r"stages\[0\]\.nodes\[0\]\.agent"):
        validate_template_agents(config, allowed_agents=["claude_code"])


def test_the_rules_the_vault_cannot_answer_are_skipped_when_unknown() -> None:
    """``None`` means "not checked here", not "checked and passed"."""
    config = {
        "stages": [
            {
                "key": "d",
                "name": "D",
                "nodes": [{"key": "n", "name": "N", "type": "ai", "agent": "anything"}],
            }
        ]
    }

    validate_template_agents(config)
