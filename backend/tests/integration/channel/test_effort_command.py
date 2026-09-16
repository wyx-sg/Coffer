"""`/effort` — the second half of the model choice, from a chat (FR-013).

`/model`'s sibling: no argument reports what is in effect (or renders a card
where the transport takes one), an argument applies it to the next turn of the
SAME conversation, and a card tap takes exactly the same path as the text.

What these pin that `/model`'s own tests cannot: the levels are asked for
against the MODEL in effect rather than the agent, and an agent whose model
takes no level must say so rather than render an empty card.
"""

from __future__ import annotations

from typing import Any

from coffer.application.channel.selection_cards import MAX_CARD_BUTTONS, is_page_turn
from coffer.domain.channel.commands import COMMAND_ROSTER, help_text, is_group_private

from .conftest import ChannelEnv, FakeChannelAdapter, Resource, inbound, tap_event, wait_until


async def _card_channel(env: ChannelEnv) -> tuple[Resource, FakeChannelAdapter]:
    resource = await env.register_channel("tg")
    adapter = env.bind(
        resource, FakeChannelAdapter(supports_buttons=True, supports_card_update=True)
    )
    await env.pair(resource, "owner")
    return resource, adapter


async def _effort(env: ChannelEnv, resource: Resource) -> str | None:
    cfg = await env.chat.get_agent_config(await env.active_conversation(resource))
    return cfg.effort


# -- the roster (FR-049 / FR-050) ---------------------------------------------


def test_effort_is_on_the_roster_the_menu_and_help_are_built_from() -> None:
    """A command handled but absent from the roster is a drift bug: the
    platform's registered menu and the help text are both rendered from it."""
    assert "effort" in {entry.name for entry in COMMAND_ROSTER}
    assert "/effort [level]" in help_text()
    # The answer is the asker's own business, like /model and /status.
    assert is_group_private("/effort") is True


# -- text path -----------------------------------------------------------------


async def test_effort_with_a_level_applies_it_to_the_next_turn(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/effort xhigh"))
    await wait_until(lambda: any("xhigh" in t for t in adapter.texts()))

    assert await _effort(env, resource) == "xhigh"


async def test_any_level_passes_through_unvalidated(env: ChannelEnv) -> None:
    """Coffer curates no levels — the agent owns that namespace, so a level it
    has never heard of is stored and fails at the CLI next turn, not here."""
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/effort ludicrous"))
    await wait_until(lambda: any("ludicrous" in t for t in adapter.texts()))

    assert await _effort(env, resource) == "ludicrous"


async def test_no_arg_reports_the_current_level_and_the_menu(env: ChannelEnv) -> None:
    env.model_suggestions.add_efforts("builtin", ["low", "high"])
    _resource, adapter = await env.paired_channel()  # text-only transport

    await env.processor.on_message(inbound("tg", "owner", "/effort"))
    await wait_until(lambda: adapter.texts())

    [text] = [t for t in adapter.texts() if t.startswith("Effort:")]
    assert "(agent default)" in text
    assert "low, high" in text


async def test_an_agent_with_no_levels_says_so_rather_than_offering_nothing(
    env: ChannelEnv,
) -> None:
    # Nothing seeded → the model in effect takes no reasoning level.
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/effort"))
    await wait_until(lambda: adapter.texts())

    assert any("takes no reasoning-effort setting" in t for t in adapter.texts())


# -- card path -----------------------------------------------------------------


async def test_no_arg_renders_a_card_where_the_transport_takes_one(env: ChannelEnv) -> None:
    env.model_suggestions.add_efforts("builtin", ["low", "medium", "high", "xhigh"])
    _resource, adapter = await _card_channel(env)

    await env.processor.on_message(inbound("tg", "owner", "/effort"))

    [(_chat, text, buttons)] = adapter.cards
    assert [b.value for b in buttons] == [
        "effort:low",
        "effort:medium",
        "effort:high",
        "effort:xhigh",
    ]
    assert "/effort <level>" in text  # the typed path is still one message away
    assert len(buttons) <= MAX_CARD_BUTTONS


async def test_an_agent_with_no_levels_renders_no_card_at_all(env: ChannelEnv) -> None:
    _resource, adapter = await _card_channel(env)

    await env.processor.on_message(inbound("tg", "owner", "/effort"))

    assert adapter.cards == []
    assert any("takes no reasoning-effort setting" in t for t in adapter.texts())


async def test_a_card_tap_applies_the_level_and_moves_the_tick(env: ChannelEnv) -> None:
    env.model_suggestions.add_efforts("builtin", ["low", "medium", "high"])
    resource, adapter = await _card_channel(env)

    await env.processor.on_callback(
        tap_event("tg", "owner", "effort:medium", platform_message_id="card-1")
    )
    await wait_until(lambda: len(adapter.card_updates) == 1)

    assert await _effort(env, resource) == "medium"
    _chat, _mid, _text, buttons, title = adapter.card_updates[0]
    assert title == "Effort"
    assert [b.value for b in buttons if b.label.endswith("✓")] == ["effort:medium"]


async def test_the_levels_follow_the_model_in_effect(env: ChannelEnv) -> None:
    """The menu belongs to the MODEL, not the agent: after `/model` pins one,
    the card offers that model's levels rather than the unpinned stand-in's."""
    env.model_suggestions.add("builtin", ["gpt-5"])
    env.model_suggestions.add_efforts("builtin", ["low", "medium", "high", "xhigh"])
    env.model_suggestions.add_efforts("builtin", ["low", "high"], model="gpt-5")
    resource, adapter = await _card_channel(env)

    await env.processor.on_message(inbound("tg", "owner", "/model gpt-5"))
    await wait_until(lambda: _model_is(env, resource, "gpt-5"))
    adapter.cards.clear()
    await env.processor.on_message(inbound("tg", "owner", "/effort"))

    [(_chat, _text, buttons)] = adapter.cards
    assert [b.value for b in buttons] == ["effort:low", "effort:high"]


async def test_a_page_turn_on_the_effort_card_changes_nothing(env: ChannelEnv) -> None:
    """`page:effort:<n>` must reach the re-render path, not the apply path —
    the kind allowlist in ``parse_page_turn`` is what decides that."""
    env.model_suggestions.add_efforts("builtin", [f"level-{i}" for i in range(12)])
    resource, adapter = await _card_channel(env)

    await env.processor.on_message(inbound("tg", "owner", "/effort"))
    [(_chat, text, buttons)] = adapter.cards
    assert "Page 1/" in text
    assert [b.value for b in buttons if is_page_turn(b.value)] == ["page:effort:1"]

    await env.processor.on_callback(
        tap_event("tg", "owner", "page:effort:1", platform_message_id="card-1")
    )
    await wait_until(lambda: len(adapter.card_updates) == 1)

    assert await _effort(env, resource) is None
    assert not any("Effort set to" in t for t in adapter.texts())


def _model_is(env: ChannelEnv, resource: Resource, model: str) -> Any:
    """Await-free probe for ``wait_until`` (the read is itself async)."""

    async def _read() -> bool:
        cfg = await env.chat.get_agent_config(await env.active_conversation(resource))
        return cfg.model == model

    return _read()
