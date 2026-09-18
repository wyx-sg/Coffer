"""A node's type names WHO does the work, and nothing else (FR-067)."""

from __future__ import annotations

import pytest

from coffer.domain.workflow.run import NodeAction, NodeStatus
from coffer.domain.workflow.template import NodeType
from coffer.domain.workflow.transitions import allowed_node_actions


def test_there_are_exactly_two_types_and_each_names_an_executor() -> None:
    # It was four. `coding` and `notification` sat beside `ai` and did exactly
    # what `ai` did, so they described what the work was ABOUT — which a task's
    # own name and instructions already say. A third for a step that runs a
    # fixed program belongs here only once Coffer can run one.
    assert {t.value for t in NodeType} == {"ai", "manual"}


@pytest.mark.acceptance(spec="workflow", scenario="a node's type says who does the work")
def test_the_type_narrows_exactly_one_thing_and_it_is_the_turn() -> None:
    """The engine reads this field for one decision: is there an agent to talk
    to? `feedback` is a message to an agent mid-turn, and a manual step has no
    agent and no turn — everything else means the same for both."""
    for status in NodeStatus:
        agent = allowed_node_actions(status, NodeType.AI)
        person = allowed_node_actions(status, NodeType.MANUAL)
        assert agent - person <= {NodeAction.FEEDBACK}
        assert person <= agent


def test_a_manual_step_is_still_a_step() -> None:
    # Completing, skipping, retrying and restoring are not an agent's
    # privileges — a human step that could not be completed would be a dead
    # end. `WAITING_REVIEW` rather than `RUNNING`: while a turn is in flight
    # the node belongs to the agent and accepts no action at all.
    waiting = allowed_node_actions(NodeStatus.WAITING_REVIEW, NodeType.MANUAL)
    assert {NodeAction.COMPLETE, NodeAction.RETRY, NodeAction.SKIP} <= waiting
    # …and the one thing it cannot be given is the one that needs an agent.
    assert NodeAction.FEEDBACK not in waiting
