"""The shipped template is a valid template, and it assumes nothing (FR-009).

The seed cannot discover a malformed built-in — it swallows its own failures so
a bad document cannot stop a daemon starting, which means a typo here would
show up as a vault that quietly never got its workflow. This is the test that
would fail instead.
"""

from __future__ import annotations

from coffer.domain.resource import validate_resource_name
from coffer.domain.workflow.builtin import (
    BUILTIN_TEMPLATE_NAME,
    BUILTIN_TEMPLATE_UID,
    builtin_template_config,
)
from coffer.domain.workflow.template import parse_template


def test_the_built_in_parses_against_a_vault_that_has_registered_nothing() -> None:
    # Empty collections, not None: `None` means "do not check", and the claim
    # under test is that the document passes the check, not that it skips it.
    template = parse_template(builtin_template_config(), known_skills=(), allowed_agents=())

    assert [stage.key for stage in template.stages] == [
        "understand",
        "plan",
        "implement",
        "verify",
        "report",
    ]
    assert template.description
    for _stage, node in template.ordered_nodes():
        assert node.skill is None
        assert node.agent is None
        # Prose that says what the task owes, not a brief that names a tool.
        assert node.instructions and len(node.instructions) > 80


def test_every_task_owes_a_required_deliverable() -> None:
    template = parse_template(builtin_template_config())

    owed = {
        node.key: [a.name for a in node.required_artifacts] for _s, node in template.ordered_nodes()
    }
    assert owed == {
        "understand": ["understanding.md"],
        "plan": ["plan.md"],
        # Declares none of its own — what it produces is the change — and is
        # read back owing the default (FR-072).
        "implement": ["report.md"],
        "verify": ["verification.md"],
        "report": ["report.md"],
    }
    found = template.node("implement")
    assert found is not None
    assert found[1].artifacts == ()


def test_the_config_is_a_fresh_copy_each_time() -> None:
    first = builtin_template_config()
    first["stages"].clear()

    assert len(builtin_template_config()["stages"]) == 5


def test_the_seeded_identity_and_label_are_usable_as_they_stand() -> None:
    validate_resource_name(BUILTIN_TEMPLATE_NAME)
    assert len(BUILTIN_TEMPLATE_UID) == 32
    assert BUILTIN_TEMPLATE_UID.isalnum()
