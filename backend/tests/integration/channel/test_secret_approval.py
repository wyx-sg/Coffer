"""A channel whose secret waits for approval says so, and starts once approved.

Spec channels "Report a channel whose secret waits for approval".
"""

from __future__ import annotations

import pytest

from coffer.application.channel.runtime import ChannelRuntime
from coffer.domain.secret_errors import SecretBindingPending, SecretBindingRejected

from .conftest import ChannelEnv


def _runtime(env: ChannelEnv, outcome: list[Exception | None]) -> ChannelRuntime:
    """A runtime whose adapter factory raises the next scripted outcome (or builds)."""

    async def factory(uid: str, config: dict[str, object]) -> object:
        step = outcome[0]
        if step is not None:
            raise step
        return await env.adapter_factory(uid, config)

    return ChannelRuntime(
        resources=env.resources,
        adapter_factory=factory,  # type: ignore[arg-type]
        processor=env.processor,
        pairing=env.pairing,
        interval_seconds=0.05,
    )


@pytest.mark.acceptance(
    spec="channels",
    scenario="a channel whose secret waits for approval says so and starts once approved",
)
async def test_pending_secret_is_reported_then_cleared_when_approved(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    outcome: list[Exception | None] = [SecretBindingPending(["a1"], ["send it to telegram"])]
    runtime = _runtime(env, outcome)
    service = env.service_for(runtime)

    await runtime.reconcile_once()
    status = await service.status(resource.uid)
    assert status.running is False
    assert status.secret_approval is not None
    assert status.secret_approval.state == "pending"
    assert status.secret_approval.secret_ref == "channel/tg/bot-token"

    # The owner approves; the next retry (the failure latch expires) starts it
    # with no restart call.
    outcome[0] = None
    runtime._failed_at.clear()
    await runtime.reconcile_once()
    status = await service.status(resource.uid)
    assert status.running is True
    assert status.secret_approval is None


async def test_refused_secret_is_reported_as_refused(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    runtime = _runtime(env, [SecretBindingRejected(["a1"], ["send it to telegram"])])

    await runtime.reconcile_once()

    status = await env.service_for(runtime).status(resource.uid)
    assert status.secret_approval is not None
    assert status.secret_approval.state == "refused"


async def test_another_start_failure_is_not_blamed_on_approval(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    runtime = _runtime(env, [RuntimeError("boom")])

    await runtime.reconcile_once()

    status = await env.service_for(runtime).status(resource.uid)
    assert status.running is False
    assert status.secret_approval is None
