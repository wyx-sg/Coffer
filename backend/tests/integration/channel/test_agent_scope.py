"""A channel routes only to the agents in its scope.

See spec channels "Limit the agents a channel may drive to its scope".

A channel's framework-level per-agent scope (ADR per-agent-resource-scope) is read the opposite
way round from every other kind's: a channel is an inbound surface no agent
consumes, so its scope names the agents the channel may DRIVE.

Two things must agree, or the owner is offered an agent the very next check
rejects: the list an unknown `/new <agent>` answers with, and the validation of
the name typed. The dormant case (an empty agent list) is
the runtime's: such a channel never starts, so it accepts no turn at all.
"""

from __future__ import annotations

import pytest

from coffer.domain.errors import ConfigValidationError, ScopeInvalidError
from coffer.domain.scope import Scope

from .conftest import (
    DEFAULT_AGENT_KEY,
    ChannelEnv,
    FakeChannelAdapter,
    Resource,
    inbound,
    tap_event,
    uid_of,
    wait_until,
)


async def _scoped(
    env: ChannelEnv, scope: Scope | None, *, buttons: bool = False
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
async def test_an_out_of_scope_agent_is_unknown_and_not_listed(env: ChannelEnv) -> None:
    resource, adapter = await _scoped(env, Scope(agents=["builtin"]))

    await env.processor.on_message(inbound("tg", "owner", "/new codex"))

    [text] = adapter.texts()
    assert text == "Unknown agent 'codex'. Available: Coffer Assistant (builtin)"
    assert await env.thread_preferred_agent(resource) is None  # nothing stuck
    assert await env.active_conversation(resource) is None


async def test_an_agent_tap_outside_the_scope_switches_nothing(env: ChannelEnv) -> None:
    """An agent card rendered before the scope narrowed still carries the old
    agent; its tap is refused and nothing sticks."""
    resource, adapter = await _scoped(env, Scope(agents=["builtin"]), buttons=True)

    await env.processor.on_callback(tap_event("tg", "owner", "agent:codex"))

    assert adapter.texts() == ["That agent is no longer one this bot may use — send /new."]
    assert await env.thread_preferred_agent(resource) is None
    assert await env.active_conversation(resource) is None


async def test_switch_inside_the_scope_still_works(env: ChannelEnv) -> None:
    resource, _adapter = await _scoped(env, Scope(agents=["builtin", "codex"]))

    await env.processor.on_message(inbound("tg", "owner", "/new codex"))

    assert await env.thread_preferred_agent(resource) == "codex"
    conv = await env.chat.get_conversation(await env.active_conversation(resource))
    assert conv.agent_key == "codex"


async def test_an_unscoped_channel_offers_every_agent(env: ChannelEnv) -> None:
    """``scope is None`` is the pre-scope default and must be untouched, which
    is why channels need no data migration."""
    _resource, adapter = await _scoped(env, None)

    await env.processor.on_message(inbound("tg", "owner", "/new nobody"))

    [text] = adapter.texts()
    assert "Coffer Assistant (builtin)" in text
    assert "Codex (codex)" in text


@pytest.mark.acceptance(spec="channels", scenario="/new starts a fresh conversation")
async def test_a_sticky_agent_narrowed_out_falls_back_to_the_channel_default(
    env: ChannelEnv,
) -> None:
    """Someone switched to codex, then the owner narrowed the channel to the
    default agent only. The next conversation must not open on codex."""
    resource, _adapter = await _scoped(env, Scope(agents=["builtin", "codex"]))
    await env.processor.on_message(inbound("tg", "owner", "/new codex"))
    assert await env.thread_preferred_agent(resource) == "codex"

    # The runtime rebinds the channel with the narrowed scope.
    env.processor.unbind(resource.uid)
    env.bind(resource, FakeChannelAdapter(), agent_scope=Scope(agents=["builtin"]))

    await env.processor.on_message(inbound("tg", "owner", "/new"))
    await wait_until(lambda: True)

    conv = await env.chat.get_conversation(await env.active_conversation(resource))
    assert conv.agent_key == "builtin"


async def test_a_channel_cannot_be_scoped_to_no_agent(env: ChannelEnv) -> None:
    """An empty agent list is refused on the write path; a channel that should
    drive nothing is switched off instead."""
    resource = await env.register_channel("tg")
    with pytest.raises(ScopeInvalidError):
        await env.resources.update_scope(resource.uid, Scope(agents=[]), actor="test")

    await env.runtime.reconcile_once()
    assert (await env.resources.get(resource.uid)).scope is None
    assert env.runtime.is_running(uid_of("tg")) is True


async def test_narrowing_a_scope_past_the_default_agent_never_reaches_the_runtime(
    env: ChannelEnv,
) -> None:
    """The gate above cannot be reached this way any more. A narrowing that
    excludes the channel's own ``default_agent`` is refused on the write path
    (the kind's ``validate_scope_for``), so a running channel cannot be taken
    offline by a scope edit that looked like it succeeded."""
    resource = await env.register_channel("tg")
    await env.runtime.reconcile_once()
    assert env.runtime.is_running(uid_of("tg")) is True

    other = await env.agent_uid("codex")
    with pytest.raises(ScopeInvalidError, match="unable to drive anything"):
        await env.resources.update_scope(resource.uid, Scope(agents=[other]), actor="test")

    await env.runtime.reconcile_once()
    assert env.runtime.is_running(uid_of("tg")) is True
    assert (await env.resources.get(resource.uid)).scope is None


async def test_widening_a_scope_rebinds_without_a_daemon_restart(env: ChannelEnv) -> None:
    """A scope edit must reach `/new <agent>` within a tick, so the binding's snapshot
    is part of what the reconciler compares."""
    mine = await env.agent_uid(DEFAULT_AGENT_KEY)
    resource = await env.register_channel("tg")
    await env.resources.update_scope(resource.uid, Scope(agents=[mine]), actor="test")
    await env.runtime.reconcile_once()
    binding = env.processor.binding(uid_of("tg"))
    assert binding is not None
    assert binding.agent_scope == Scope(agents=[DEFAULT_AGENT_KEY])

    await env.resources.update_scope(resource.uid, None, actor="test")
    await env.runtime.reconcile_once()

    binding = env.processor.binding(uid_of("tg"))
    assert env.runtime.is_running(uid_of("tg")) is True
    assert binding is not None
    assert binding.agent_scope is None


@pytest.mark.acceptance(
    spec="channels", scenario="a channel's scope names agent resources, not agent keys"
)
async def test_narrowing_to_the_channels_own_agent_is_accepted(env: ChannelEnv) -> None:
    """The narrowing a user actually makes, end to end.

    There is one vocabulary now: a scope and a ``default_agent`` both hold the
    UID of an agent row, which is also what the reach picker offers. While the
    scope held a resource NAME and the default held an agent KEY, this exact
    edit — narrowing a channel to the only value the picker could produce — was
    refused, and the only value that passed was one the picker then had to
    render as an agent registered nowhere.

    The agent KEY survives in exactly one place, below the gate: the binding,
    because that is what the turn platform dispatches on.
    """
    await env.register_agent_resource("my-codex", "codex")
    mine = await env.agent_uid(DEFAULT_AGENT_KEY)
    resource = await env.register_channel("tg")
    await env.runtime.reconcile_once()
    assert env.runtime.is_running(uid_of("tg")) is True

    await env.resources.update_scope(resource.uid, Scope(agents=[mine]), actor="test")
    await env.runtime.reconcile_once()

    assert env.runtime.is_running(uid_of("tg")) is True
    # ...and the binding carries it in the vocabulary everything below the gate
    # reads — `/new <agent>` and the routing of a chosen key.
    binding = env.processor.binding(uid_of("tg"))
    assert binding is not None
    assert binding.agent_scope == Scope(agents=[DEFAULT_AGENT_KEY])


async def test_narrowing_past_the_default_agent_is_still_refused(env: ChannelEnv) -> None:
    """One vocabulary must not soften the invariant: a scope that genuinely
    excludes the channel's own agent is still refused, and the refusal still
    names — in labels — the agent it excluded."""
    await env.register_agent_resource("my-codex", "codex")
    other = await env.agent_uid("codex", name="my-codex")
    resource = await env.register_channel("tg")

    with pytest.raises(ScopeInvalidError, match=DEFAULT_AGENT_KEY):
        await env.resources.update_scope(resource.uid, Scope(agents=[other]), actor="test")

    assert (await env.resources.get(resource.uid)).scope is None


@pytest.mark.acceptance(
    spec="channels", scenario="a channel bound to an agent that does not exist is refused"
)
async def test_registering_a_channel_bound_to_no_such_agent_is_refused(env: ChannelEnv) -> None:
    """Through the real ``ResourceService.register``, not the hook alone.

    The hook is async now — a uid is only checkable against the resource table —
    and an async validator the framework forgot to await is a validator that
    passes everything in silence. Driving registration end to end is what makes
    that failure impossible to ship: the row must not exist afterwards.
    """
    # One real agent, so the registry has something to say. An EMPTY registry
    # cannot answer "is this registered" at all, and the check skips rather than
    # blocking every channel write on a vault that has no agents yet.
    await env.agent_uid(DEFAULT_AGENT_KEY)
    env.keyring.set("channel/tg/bot-token", "secret")

    with pytest.raises(ConfigValidationError, match="not a registered agent"):
        await env.resources.register(
            kind="channel",
            name="tg",
            config={
                "channel_type": "telegram",
                "bot_token_ref": "channel/tg/bot-token",
                "default_agent": "uid-of-an-agent-that-does-not-exist",
            },
            actor="test",
        )

    assert await env.resources.list(kind="channel") == []


@pytest.mark.acceptance(spec="channels", scenario="a channel bound to no agent never starts")
async def test_a_channel_bound_to_no_agent_never_starts(env: ChannelEnv) -> None:
    """No substitute. There is no value a schema could default to — a uid is
    minted per vault — so a channel nobody bound stays dark and says why."""
    env.keyring.set("channel/tg/bot-token", "secret")
    await env.resources.register(
        kind="channel",
        name="tg",
        config={"channel_type": "telegram", "bot_token_ref": "channel/tg/bot-token"},
        actor="test",
    )

    await env.runtime.reconcile_once()

    assert env.runtime.is_running(uid_of("tg")) is False
    assert env.created_adapters == []
