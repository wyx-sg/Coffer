"""A channel routes only to the agents in its scope (spec channels FR-072).

A channel's framework-level per-agent scope (ADR per-agent-resource-scope) is read the opposite
way round from every other kind's: a channel is an inbound surface no agent
consumes, so its scope names the agents the channel may DRIVE.

Three things must agree, or the owner sees a card offering an agent the very
next check rejects: the `/agent` listing, the `/agent` card, and the validation
of a chosen key (typed or tapped). The dormant case (`scope == []`) is the
runtime's: such a channel never starts, so it accepts no turn at all.
"""

from __future__ import annotations

import pytest

from coffer.domain.errors import ScopeInvalidError

from .conftest import ChannelEnv, FakeChannelAdapter, Resource, inbound, tap_event, wait_until


async def _scoped(
    env: ChannelEnv, scope: list[str] | None, *, buttons: bool = False
) -> tuple[Resource, FakeChannelAdapter]:
    """A paired channel scoped to ``scope``, with a second agent registered so
    there is something for the scope to narrow away."""
    env.add_agent("codex", reply="codex-here")
    resource = await env.register_channel("tg")
    adapter = env.bind(
        resource,
        FakeChannelAdapter(supports_buttons=buttons, supports_card_update=buttons),
        agent_scope=scope,
    )
    await env.pair(resource, "owner")
    return resource, adapter


@pytest.mark.acceptance(
    spec="channels", scenario="a channel may only route to the agents in its scope"
)
async def test_agent_listing_is_narrowed_to_the_scope(env: ChannelEnv) -> None:
    _resource, adapter = await _scoped(env, ["builtin"])

    await env.processor.on_message(inbound("tg", "owner", "/agent"))

    [text] = adapter.texts()
    assert "Available: builtin" in text
    assert "codex" not in text


async def test_agent_card_is_narrowed_to_the_scope(env: ChannelEnv) -> None:
    """The card must offer exactly what the validator accepts — a card that
    offers an out-of-scope agent is the failure this narrowing exists for."""
    _resource, adapter = await _scoped(env, ["builtin"], buttons=True)

    await env.processor.on_message(inbound("tg", "owner", "/agent"))

    [(_chat, _text, buttons)] = adapter.cards
    assert [b.value for b in buttons] == ["agent:builtin"]


async def test_typed_switch_to_an_out_of_scope_agent_is_refused(env: ChannelEnv) -> None:
    resource, adapter = await _scoped(env, ["builtin"])

    await env.processor.on_message(inbound("tg", "owner", "/agent codex"))

    assert any("Unknown agent 'codex'" in t for t in adapter.texts())
    assert await env.thread_preferred_agent(resource) is None  # nothing stuck


async def test_tapped_switch_to_an_out_of_scope_agent_is_refused(env: ChannelEnv) -> None:
    """A stale card (rendered before the scope was narrowed) must not become a
    way past the check."""
    resource, adapter = await _scoped(env, ["builtin"], buttons=True)

    await env.processor.on_callback(tap_event("tg", "owner", "agent:codex"))

    assert any("codex" in t for t in adapter.texts())
    assert await env.thread_preferred_agent(resource) is None


async def test_switch_inside_the_scope_still_works(env: ChannelEnv) -> None:
    resource, _adapter = await _scoped(env, ["builtin", "codex"])

    await env.processor.on_message(inbound("tg", "owner", "/agent codex"))
    await wait_until(lambda: True)

    assert await env.thread_preferred_agent(resource) == "codex"
    conv = await env.chat.get_conversation(await env.active_conversation(resource))
    assert conv.agent_key == "codex"


async def test_an_unscoped_channel_offers_every_agent(env: ChannelEnv) -> None:
    """``scope is None`` is the pre-scope default and must be untouched, which
    is why channels need no data migration."""
    _resource, adapter = await _scoped(env, None)

    await env.processor.on_message(inbound("tg", "owner", "/agent"))

    [text] = adapter.texts()
    assert "builtin" in text
    assert "codex" in text


async def test_a_sticky_agent_narrowed_out_falls_back_to_the_channel_default(
    env: ChannelEnv,
) -> None:
    """Someone switched to codex, then the owner narrowed the channel to the
    default agent only. The next conversation must not open on codex."""
    resource, _adapter = await _scoped(env, ["builtin", "codex"])
    await env.processor.on_message(inbound("tg", "owner", "/agent codex"))
    await wait_until(lambda: True)
    assert await env.thread_preferred_agent(resource) == "codex"

    # The runtime rebinds the channel with the narrowed scope.
    env.processor.unbind(resource.name)
    env.bind(resource, FakeChannelAdapter(), agent_scope=["builtin"])

    await env.processor.on_message(inbound("tg", "owner", "/new"))
    await wait_until(lambda: True)

    conv = await env.chat.get_conversation(await env.active_conversation(resource))
    assert conv.agent_key == "builtin"


@pytest.mark.acceptance(spec="channels", scenario="a channel scoped to no agent is dormant")
async def test_a_channel_scoped_to_no_agent_is_never_started(env: ChannelEnv) -> None:
    """The dormant case fails early rather than per-turn: the reconciler simply
    does not start the adapter, so the channel accepts nothing to refuse."""
    resource = await env.register_channel("tg")
    await env.resources.update_scope(resource.ref, [], actor="test")

    await env.runtime.reconcile_once()

    assert env.runtime.is_running("tg") is False
    assert env.created_adapters == []


async def test_narrowing_a_scope_past_the_default_agent_never_reaches_the_runtime(
    env: ChannelEnv,
) -> None:
    """The gate above cannot be reached this way any more. A narrowing that
    excludes the channel's own ``default_agent`` is refused on the write path
    (the kind's ``validate_scope_for``), so a running channel cannot be taken
    offline by a scope edit that looked like it succeeded."""
    resource = await env.register_channel("tg")
    await env.runtime.reconcile_once()
    assert env.runtime.is_running("tg") is True

    with pytest.raises(ScopeInvalidError, match="claude_code"):
        await env.resources.update_scope(resource.ref, ["codex"], actor="test")

    await env.runtime.reconcile_once()
    assert env.runtime.is_running("tg") is True
    assert (await env.resources.get(resource.ref)).scope is None


async def test_widening_a_scope_rebinds_without_a_daemon_restart(env: ChannelEnv) -> None:
    """A scope edit must reach `/agent` within a tick, so the binding's snapshot
    is part of what the reconciler compares. Uses the dormant scope, now the
    only narrowing that can stop a running channel."""
    resource = await env.register_channel("tg")
    await env.resources.update_scope(resource.ref, [], actor="test")
    await env.runtime.reconcile_once()
    assert env.runtime.is_running("tg") is False

    await env.resources.update_scope(resource.ref, None, actor="test")
    await env.runtime.reconcile_once()

    assert env.runtime.is_running("tg") is True
