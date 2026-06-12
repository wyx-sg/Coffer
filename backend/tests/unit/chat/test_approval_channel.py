"""Unit tests for ApprovalChannel — the concrete ApprovalGate."""

from __future__ import annotations

import asyncio

import pytest

from coffer.application.chat.approvals import ApprovalChannel
from coffer.application.chat.ports import ApprovalDecision
from coffer.domain.errors import ApprovalNotFound


@pytest.mark.asyncio
async def test_wait_returns_the_resolved_decision() -> None:
    channel = ApprovalChannel()
    waiter = asyncio.ensure_future(channel.wait("r1"))
    await asyncio.sleep(0)  # let wait() register its pending future

    channel.resolve("r1", ApprovalDecision(behavior="allow", message="ok"))

    decision = await asyncio.wait_for(waiter, timeout=1.0)
    assert decision.behavior == "allow"
    assert decision.message == "ok"


@pytest.mark.asyncio
async def test_resolve_unknown_request_raises() -> None:
    channel = ApprovalChannel()
    with pytest.raises(ApprovalNotFound):
        channel.resolve("missing", ApprovalDecision(behavior="deny"))


@pytest.mark.asyncio
async def test_decision_arriving_before_wait_is_delivered() -> None:
    """A decision posted after the request is registered but before the adapter
    reaches wait() must still be delivered (no spurious ApprovalNotFound)."""
    channel = ApprovalChannel()
    channel.register("r1")  # orchestrator registers when it forwards the event

    # Client decides before the adapter parks in wait().
    channel.resolve("r1", ApprovalDecision(behavior="allow"))

    decision = await asyncio.wait_for(channel.wait("r1"), timeout=1.0)
    assert decision.behavior == "allow"


@pytest.mark.asyncio
async def test_resolve_still_rejects_unregistered_request() -> None:
    """Registering one id must not make every id resolvable — an unknown id is
    still rejected."""
    channel = ApprovalChannel()
    channel.register("r1")
    with pytest.raises(ApprovalNotFound):
        channel.resolve("other", ApprovalDecision(behavior="deny"))


@pytest.mark.asyncio
async def test_resolve_a_second_time_raises() -> None:
    channel = ApprovalChannel()
    waiter = asyncio.ensure_future(channel.wait("r1"))
    await asyncio.sleep(0)

    channel.resolve("r1", ApprovalDecision(behavior="allow"))
    await asyncio.wait_for(waiter, timeout=1.0)

    # The request has been consumed; a repeat decision is rejected.
    with pytest.raises(ApprovalNotFound):
        channel.resolve("r1", ApprovalDecision(behavior="deny"))


@pytest.mark.asyncio
async def test_wait_raises_cancelled_when_the_turn_is_interrupted() -> None:
    channel = ApprovalChannel()
    waiter = asyncio.ensure_future(channel.wait("r1"))
    await asyncio.sleep(0)

    waiter.cancel()  # the turn task is cancelled while waiting on approval

    with pytest.raises(asyncio.CancelledError):
        await waiter
