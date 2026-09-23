"""Skipping a node nobody started.

A regression, and an honest one: the transition table says a ``pending`` node
accepts ``skip``, and the HTTP surface reports exactly what that table allows —
but the service used to refuse every action other than ``start`` when no attempt
row existed yet. So a Skip button was offered on a node that had never run, and
pressing it answered 409.

The fix is in ``NodeOps.attempt_for_action``: a skip with no attempt opens one
and settles it in the same breath, which is also the behaviour a person expects
when a stage turns out not to apply before any work goes into it.
"""

from __future__ import annotations

from coffer.domain.workflow.run import NodeAction, NodeStatus

from .conftest import Engine


async def test_a_node_that_never_started_can_be_skipped(engine: Engine) -> None:
    """`skip` is legal on `pending`, so it must also be possible."""
    run = await engine.started()

    result = await engine.nodes.act(run.id, "draft_td", NodeAction.SKIP, version=run.version)

    attempt = result.attempt
    assert attempt is not None
    assert attempt.status == NodeStatus.SKIPPED.value
    # Attempt 1, not 2: nothing was tried, so nothing was retried.
    assert attempt.attempt == 1


async def test_skipping_an_unstarted_node_lets_the_run_move_on(engine: Engine) -> None:
    """The skipped node counts as settled, so the walk offers the next one."""
    run = await engine.started()

    await engine.nodes.act(run.id, "draft_td", NodeAction.SKIP, version=run.version)
    position = await engine.nodes.next_position(run.id)

    assert position is not None
    assert position.node_key != "draft_td"
