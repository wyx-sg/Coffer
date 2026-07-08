"""Interactive selection cards for /agent and /model (P3, FR-013/FR-017).

When a channel ``supports_buttons``, the no-arg command renders a selection
card; a tap is owner-gated and routed to the same switch the text command
performs. Text-only channels keep today's behavior (covered in test_routing).
"""

from __future__ import annotations

import pytest

from .conftest import ChannelEnv, FakeChannelAdapter, Resource, inbound, tap_event, wait_until


async def _card_channel(
    env: ChannelEnv, *, sender_id: str | None = None
) -> tuple[Resource, FakeChannelAdapter]:
    """A paired channel whose adapter advertises button support."""
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_buttons=True))
    await env.pair(resource, "owner", sender_id=sender_id)
    return resource, adapter


# -- /agent card ---------------------------------------------------------------


async def test_agent_no_arg_renders_a_card_when_supported(env: ChannelEnv) -> None:
    env.add_agent("codex")
    _resource, adapter = await _card_channel(env)

    await env.processor.on_message(inbound("tg", "owner", "/agent"))

    assert len(adapter.cards) == 1
    _chat, _text, buttons = adapter.cards[0]
    assert [b.value for b in buttons] == ["agent:builtin", "agent:codex"]
    # The current agent (the channel default, builtin) is marked.
    assert any(b.label.endswith("✓") for b in buttons)


@pytest.mark.acceptance(spec="009-channels", scenario="a selection-card tap switches the agent")
async def test_agent_card_tap_switches_and_sticks(env: ChannelEnv) -> None:
    env.add_agent("codex", reply="codex-here")
    resource, _adapter = await _card_channel(env)

    await env.processor.on_callback(tap_event("tg", "owner", "agent:codex"))
    await wait_until(lambda: True)

    assert await env.thread_preferred_agent(resource) == "codex"
    conv = await env.chat.get_conversation(await env.active_conversation(resource))
    assert conv.agent_key == "codex"


async def test_agent_card_tap_rejects_unknown_key(env: ChannelEnv) -> None:
    resource, adapter = await _card_channel(env)

    await env.processor.on_callback(tap_event("tg", "owner", "agent:ghost"))

    assert any("ghost" in t for t in adapter.texts())
    assert await env.thread_preferred_agent(resource) is None  # unchanged


# -- /model card ---------------------------------------------------------------


async def test_model_no_arg_renders_card_from_suggestions(env: ChannelEnv) -> None:
    env.model_suggestions.add("builtin", ["claude-opus-4-8", "claude-haiku-4-5"])
    _resource, adapter = await _card_channel(env)

    await env.processor.on_message(inbound("tg", "owner", "/model"))

    [(_chat, _text, buttons)] = adapter.cards
    assert [b.value for b in buttons] == ["model:claude-opus-4-8", "model:claude-haiku-4-5"]


async def test_model_no_arg_falls_back_to_text_without_suggestions(env: ChannelEnv) -> None:
    # No suggestions seeded → no buttons to render → plain text, no card.
    _resource, adapter = await _card_channel(env)

    await env.processor.on_message(inbound("tg", "owner", "/model"))

    assert adapter.cards == []
    assert any("Model:" in t for t in adapter.texts())


async def test_model_card_tap_sets_next_turn_model(env: ChannelEnv) -> None:
    env.model_suggestions.add("builtin", ["claude-opus-4-8"])
    resource, _adapter = await _card_channel(env)

    await env.processor.on_callback(tap_event("tg", "owner", "model:claude-opus-4-8"))

    cfg = await env.chat.get_agent_config(await env.active_conversation(resource))
    assert cfg.model == "claude-opus-4-8"


# -- owner gate ----------------------------------------------------------------


@pytest.mark.acceptance(spec="009-channels", scenario="a non-owner selection-card tap is ignored")
async def test_non_owner_tap_is_ignored(env: ChannelEnv) -> None:
    env.add_agent("codex")
    resource, _adapter = await _card_channel(env, sender_id="owner-1")

    # Right chat, wrong member — the tap must not flip the owner's agent.
    await env.processor.on_callback(tap_event("tg", "owner", "agent:codex", sender_id="intruder-9"))

    assert await env.thread_preferred_agent(resource) is None


async def test_tap_from_unbound_channel_is_ignored(env: ChannelEnv) -> None:
    # No binding registered for this channel name → silently dropped, no crash.
    await env.processor.on_callback(tap_event("ghost", "owner", "agent:codex"))
