"""Interactive selection cards for /agent and /model (P3, FR-013/FR-017).

When a channel ``supports_buttons``, the no-arg command renders a selection
card; a tap is owner-gated and routed to the same switch the text command
performs. Text-only channels keep today's behavior (covered in test_routing).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from coffer.application.channel.selection_cards import MAX_MODEL_PICKS
from coffer.domain.channel.envelopes import ChoiceButton
from coffer.domain.channel.errors import ChannelSendFailed

from .conftest import ChannelEnv, FakeChannelAdapter, Resource, inbound, tap_event, wait_until


def _refuse_cards(adapter: FakeChannelAdapter) -> None:
    """Make the transport answer a CARD send the way SeaTalk answered the
    29-button ``/model`` card: an outright rejection. Plain text still works."""
    real = adapter.send_text

    async def send_text(
        chat_id: str,
        markdown: str,
        *,
        buttons: Sequence[ChoiceButton] | None = None,
        **kw: Any,
    ) -> Any:
        if buttons:
            raise ChannelSendFailed("tg", "/messaging/v2/single_chat: code=102", api_rejected=True)
        return await real(chat_id, markdown, buttons=buttons, **kw)

    adapter.send_text = send_text  # type: ignore[method-assign]


async def _card_channel(
    env: ChannelEnv, *, sender_id: str | None = None
) -> tuple[Resource, FakeChannelAdapter]:
    """A paired channel whose adapter advertises button support, and can rewrite
    a delivered card (both Telegram and SeaTalk can)."""
    resource = await env.register_channel("tg")
    adapter = env.bind(
        resource, FakeChannelAdapter(supports_buttons=True, supports_card_update=True)
    )
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


@pytest.mark.acceptance(spec="channels", scenario="a selection-card tap switches the agent")
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


async def test_a_long_catalogue_becomes_a_handful_of_quick_picks(env: ChannelEnv) -> None:
    """The suggestion port hands over the agent's whole model catalogue; the
    card carries a bounded handful of it, not all 29 buttons."""
    env.model_suggestions.add("builtin", [f"model-{i}" for i in range(29)])
    _resource, adapter = await _card_channel(env)

    await env.processor.on_message(inbound("tg", "owner", "/model"))

    [(_chat, text, buttons)] = adapter.cards
    assert len(buttons) == MAX_MODEL_PICKS
    assert "/model <name>" in text  # the rest of the catalogue stays reachable


# -- a card the platform refuses degrades to text, never to silence -------------


@pytest.mark.acceptance(
    spec="channels", scenario="a refused selection card falls back to the text reply"
)
async def test_a_refused_model_card_falls_back_to_the_text_reply(env: ChannelEnv) -> None:
    """SeaTalk refused a `/model` card outright and the command ended in
    silence — the user saw nothing at all. A refused card must degrade to the
    plain-text answer the handler already has."""
    env.model_suggestions.add("builtin", ["claude-opus-4-8"])
    _resource, adapter = await _card_channel(env)
    _refuse_cards(adapter)

    await env.processor.on_message(inbound("tg", "owner", "/model"))

    assert adapter.cards == []
    assert any("Model:" in t for t in adapter.texts())


async def test_a_refused_agent_card_falls_back_to_the_text_reply(env: ChannelEnv) -> None:
    env.add_agent("codex")
    _resource, adapter = await _card_channel(env)
    _refuse_cards(adapter)

    await env.processor.on_message(inbound("tg", "owner", "/agent"))

    assert adapter.cards == []
    assert any("Available:" in t for t in adapter.texts())


async def test_model_card_tap_sets_next_turn_model(env: ChannelEnv) -> None:
    env.model_suggestions.add("builtin", ["claude-opus-4-8"])
    resource, _adapter = await _card_channel(env)

    await env.processor.on_callback(tap_event("tg", "owner", "model:claude-opus-4-8"))

    cfg = await env.chat.get_agent_config(await env.active_conversation(resource))
    assert cfg.model == "claude-opus-4-8"


# -- owner gate ----------------------------------------------------------------


@pytest.mark.acceptance(spec="channels", scenario="a non-owner selection-card tap is ignored")
async def test_non_owner_tap_is_ignored(env: ChannelEnv) -> None:
    env.add_agent("codex")
    resource, _adapter = await _card_channel(env, sender_id="owner-1")

    # Right chat, wrong member — the tap must not flip the owner's agent.
    await env.processor.on_callback(tap_event("tg", "owner", "agent:codex", sender_id="intruder-9"))

    assert await env.thread_preferred_agent(resource) is None


async def test_tap_from_unbound_channel_is_ignored(env: ChannelEnv) -> None:
    # No binding registered for this channel name → silently dropped, no crash.
    await env.processor.on_callback(tap_event("ghost", "owner", "agent:codex"))


# -- group card taps (FR-034) --------------------------------------------------


async def _group_card_channel(
    env: ChannelEnv, *, group_id: str = "grp-1", owner: str = "owner-1"
) -> tuple[Resource, FakeChannelAdapter]:
    """A channel with a button-capable adapter and a paired GROUP peer (as the
    owner's first @mention would have created), so a group card tap resolves an
    owner + a peer row for the group chat."""
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, FakeChannelAdapter(supports_buttons=True))
    await env.pair(resource, group_id, sender_id=owner)
    return resource, adapter


@pytest.mark.acceptance(
    spec="channels", scenario="a group selection-card tap replies in the group/thread"
)
async def test_owner_group_card_tap_switches_and_replies_in_the_thread(env: ChannelEnv) -> None:
    """The owner tapping an /agent card in a group switches the agent for THAT
    group/thread and the "switched" confirmation is routed back into the group
    thread the tap came from — never a DM."""
    env.add_agent("codex", reply="codex-here")
    resource, adapter = await _group_card_channel(env)

    await env.processor.on_callback(
        tap_event(
            "tg", "grp-1", "agent:codex", sender_id="owner-1", chat_kind="group", thread_id="th-1"
        )
    )
    await wait_until(lambda: any("Switched to agent" in t for t in adapter.texts()))

    assert await env.thread_preferred_agent(resource, "grp-1", "th-1") == "codex"
    match = next(r for r in adapter.sent_routed if "Switched to agent" in r[1])
    chat_id, _text, thread_id, chat_kind = match
    assert (chat_id, thread_id, chat_kind) == ("grp-1", "th-1", "group")


async def test_owner_group_model_card_tap_replies_in_the_thread(env: ChannelEnv) -> None:
    """The parametric /model switch is likewise routed into the group thread."""
    resource, adapter = await _group_card_channel(env)

    await env.processor.on_callback(
        tap_event(
            "tg",
            "grp-1",
            "model:claude-opus-4-8",
            sender_id="owner-1",
            chat_kind="group",
            thread_id="th-1",
        )
    )
    await wait_until(lambda: any("Model set to" in t for t in adapter.texts()))

    cfg = await env.chat.get_agent_config(await env.active_conversation(resource, "grp-1", "th-1"))
    assert cfg.model == "claude-opus-4-8"
    match = next(r for r in adapter.sent_routed if "Model set to" in r[1])
    chat_id, _text, thread_id, chat_kind = match
    assert (chat_id, thread_id, chat_kind) == ("grp-1", "th-1", "group")


async def test_non_owner_group_card_tap_is_refused_and_routed(env: ChannelEnv) -> None:
    """A non-owner tapping a group card gets a refusal routed into the group
    thread and never flips the owner's agent."""
    env.add_agent("codex")
    resource, adapter = await _group_card_channel(env)

    await env.processor.on_callback(
        tap_event(
            "tg",
            "grp-1",
            "agent:codex",
            sender_id="intruder-9",
            chat_kind="group",
            thread_id="th-1",
        )
    )

    assert await env.thread_preferred_agent(resource, "grp-1", "th-1") is None
    assert len(adapter.sent_routed) == 1
    chat_id, text, thread_id, chat_kind = adapter.sent_routed[0]
    assert (chat_id, thread_id, chat_kind) == ("grp-1", "th-1", "group")
    assert "Not authorized" in text


async def test_dm_card_tap_still_replies_in_the_dm(env: ChannelEnv) -> None:
    """DM regression: a direct card tap still switches and replies as a DM
    (chat_kind="direct", no thread), unaffected by the group routing."""
    env.add_agent("codex", reply="codex-here")
    resource, adapter = await _card_channel(env, sender_id="owner-1")

    await env.processor.on_callback(tap_event("tg", "owner", "agent:codex", sender_id="owner-1"))
    await wait_until(lambda: any("Switched to agent" in t for t in adapter.texts()))

    assert await env.thread_preferred_agent(resource) == "codex"
    match = next(r for r in adapter.sent_routed if "Switched to agent" in r[1])
    chat_id, _text, thread_id, chat_kind = match
    assert (chat_id, thread_id, chat_kind) == ("owner", "", "direct")


# -- the tapped card is rewritten, not left lying --------------------------------


@pytest.mark.acceptance(
    spec="channels", scenario="a tapped selection card is rewritten with the new choice"
)
async def test_tapping_a_card_rewrites_it_with_the_new_choice(env: ChannelEnv) -> None:
    """A card that keeps offering the option the user just took is worse than no
    card: tapping it again looks like it should do something and does nothing.
    After the switch lands, the card is rewritten with the tick moved."""
    env.add_agent("codex")
    _resource, adapter = await _card_channel(env)
    adapter.card_updates.clear()

    await env.processor.on_callback(
        tap_event("tg", "owner", "agent:codex", platform_message_id="card-1")
    )

    await wait_until(lambda: len(adapter.card_updates) == 1)
    chat_id, message_id, text, buttons, title = adapter.card_updates[0]
    assert (chat_id, message_id) == ("owner", "card-1")
    assert title == "Agent"
    assert "codex" in text
    # Exactly one option is ticked, and it is the one just chosen (buttons carry
    # the display name; the value carries the key).
    ticked = [b.value for b in buttons if b.label.endswith("✓")]
    assert ticked == ["agent:codex"], f"the tick should follow the switch, got {ticked}"


async def test_a_card_is_not_rewritten_when_the_transport_cannot(env: ChannelEnv) -> None:
    """``supports_card_update`` is the gate: a transport without it must not be
    called, and the switch still succeeds."""
    env.add_agent("codex")
    resource = await env.register_channel("tg")
    # supports_card_update defaults off — the transport simply cannot.
    adapter = env.bind(resource, FakeChannelAdapter(supports_buttons=True))
    await env.pair(resource, "owner")

    await env.processor.on_callback(
        tap_event("tg", "owner", "agent:codex", platform_message_id="card-1")
    )

    await wait_until(lambda: any("codex" in text for _chat, text in adapter.sent))
    assert adapter.card_updates == []


async def test_a_failed_card_rewrite_does_not_break_the_switch(env: ChannelEnv) -> None:
    """Cosmetic by design: the card may have aged past SeaTalk's 7-day update
    window, or the platform may rate-limit us. The switch already happened and
    was confirmed in chat, so a failed rewrite is logged and dropped."""
    env.add_agent("codex")
    _resource, adapter = await _card_channel(env)

    async def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("update rejected")

    adapter.update_card = boom  # type: ignore[method-assign]

    await env.processor.on_callback(
        tap_event("tg", "owner", "agent:codex", platform_message_id="card-1")
    )

    await wait_until(lambda: any("codex" in text for _chat, text in adapter.sent))
