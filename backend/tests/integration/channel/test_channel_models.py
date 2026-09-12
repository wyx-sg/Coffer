"""The channel's own model curation, end to end (FR-071).

Curation moved off the agent and onto the channel: the agent page governs what
a person gets when they open that agent directly, and a channel is its own
place with its own audience. So a channel carries a ``default_model`` (what a
NEW conversation here opens on) and a ``models`` allowed range (what ``/model``
may reach), and those two are the only narrowing applied to a channel's picker.

Empty range = NOT CURATED throughout: a channel nobody has configured behaves
exactly as it did before this existed, which is what every "uncurated" test
below pins.
"""

from __future__ import annotations

from .conftest import ChannelEnv, FakeChannelAdapter, inbound, wait_until


async def _card_channel(
    env: ChannelEnv,
    *,
    default_model: str | None = None,
    models: tuple[str, ...] = (),
) -> tuple[object, FakeChannelAdapter]:
    """A paired, button-capable channel carrying the given curation."""
    resource = await env.register_channel("tg")
    adapter = env.bind(
        resource,
        FakeChannelAdapter(supports_buttons=True, supports_card_update=True),
        default_model=default_model,
        models=models,
    )
    await env.pair(resource, "owner")
    return resource, adapter


# -- the default model a new conversation opens on -----------------------------


async def test_a_new_conversation_starts_on_the_channels_default_model(
    env: ChannelEnv,
) -> None:
    """The channel's answer to "what does a conversation here run on" reaches
    the provider at creation, the same way ``default_agent_config`` does — it
    is the provider that then projects it onto the conversation."""
    _resource, adapter = await _card_channel(env, default_model="claude-opus-5")

    await env.processor.on_message(inbound("tg", "owner", "hello"))
    await wait_until(lambda: adapter.texts())

    assert env.provider.last_agent_config == {"model": "claude-opus-5"}


async def test_a_channel_that_pins_nothing_leaves_the_cli_default(env: ChannelEnv) -> None:
    """The out-of-the-box state: no model is written at all, so the agent's own
    CLI default decides — unchanged from before the field existed."""
    _resource, adapter = await _card_channel(env)

    await env.processor.on_message(inbound("tg", "owner", "hello"))
    await wait_until(lambda: adapter.texts())

    # ``{}``, not ``{"model": ...}``: nothing is pinned, and no model key is
    # written for the provider to project.
    assert env.provider.last_agent_config == {}


async def test_a_fresh_conversation_returns_to_the_default_model(env: ChannelEnv) -> None:
    """``/model`` re-points the conversation in hand; ``/new`` opens another
    one, and the channel's default is where that one starts."""
    resource, adapter = await _card_channel(
        env, default_model="claude-opus-5", models=("claude-opus-5", "claude-haiku-4-5")
    )

    await env.processor.on_message(inbound("tg", "owner", "/model claude-haiku-4-5"))
    await wait_until(lambda: any("claude-haiku-4-5" in t for t in adapter.texts()))
    cfg = await env.chat.get_agent_config(await env.active_conversation(resource))
    assert cfg.model == "claude-haiku-4-5"

    await env.processor.on_message(inbound("tg", "owner", "/new"))
    await wait_until(lambda: any("fresh conversation" in t for t in adapter.texts()))

    assert env.provider.last_agent_config == {"model": "claude-opus-5"}


# -- the /model card is narrowed to the channel's range ------------------------


async def test_the_model_card_offers_only_the_channels_range(env: ChannelEnv) -> None:
    """The agent offers three; the channel allows two. A card must never show a
    pick that ``/model`` would then refuse."""
    env.model_suggestions.add("builtin", ["claude-opus-5", "claude-mythos-5", "claude-haiku-4-5"])
    _resource, adapter = await _card_channel(env, models=("claude-haiku-4-5", "claude-opus-5"))

    await env.processor.on_message(inbound("tg", "owner", "/model"))

    [(_chat, _text, buttons)] = adapter.cards
    # The channel's own order, not discovery's: the user arranged that list.
    assert [b.value for b in buttons] == ["model:claude-haiku-4-5", "model:claude-opus-5"]


async def test_an_uncurated_channel_still_offers_the_whole_catalogue(
    env: ChannelEnv,
) -> None:
    env.model_suggestions.add("builtin", ["claude-opus-5", "claude-haiku-4-5"])
    _resource, adapter = await _card_channel(env)

    await env.processor.on_message(inbound("tg", "owner", "/model"))

    [(_chat, _text, buttons)] = adapter.cards
    assert [b.value for b in buttons] == ["model:claude-opus-5", "model:claude-haiku-4-5"]


async def test_the_range_stands_even_when_the_agent_suggests_nothing(
    env: ChannelEnv,
) -> None:
    """Nothing discovered, but the channel named its models — the card is still
    the channel's list, because the channel is the authority here."""
    _resource, adapter = await _card_channel(env, models=("claude-opus-5",))

    await env.processor.on_message(inbound("tg", "owner", "/model"))

    [(_chat, _text, buttons)] = adapter.cards
    assert [b.value for b in buttons] == ["model:claude-opus-5"]


# -- /model <id> outside the range is refused ----------------------------------


async def test_a_model_outside_the_range_is_refused_naming_what_is_allowed(
    env: ChannelEnv,
) -> None:
    resource, adapter = await _card_channel(env, models=("claude-opus-5", "claude-haiku-4-5"))

    await env.processor.on_message(inbound("tg", "owner", "/model claude-mythos-5"))
    await wait_until(lambda: adapter.texts())

    [text] = adapter.texts()
    assert "claude-mythos-5" in text
    assert "claude-opus-5" in text and "claude-haiku-4-5" in text
    # And nothing was switched — a refusal must not half-apply.
    cfg = await env.chat.get_agent_config(await env.active_conversation(resource))
    assert cfg.model is None


async def test_a_model_inside_the_range_still_goes_through(env: ChannelEnv) -> None:
    resource, adapter = await _card_channel(env, models=("claude-opus-5", "claude-haiku-4-5"))

    await env.processor.on_message(inbound("tg", "owner", "/model claude-haiku-4-5"))
    await wait_until(lambda: any("claude-haiku-4-5" in t for t in adapter.texts()))

    cfg = await env.chat.get_agent_config(await env.active_conversation(resource))
    assert cfg.model == "claude-haiku-4-5"


async def test_an_uncurated_channel_refuses_nothing(env: ChannelEnv) -> None:
    """Raw passthrough survives where there is no range: Coffer does not own
    the CLI's model namespace, and a bad name is the CLI's error to report."""
    resource, adapter = await _card_channel(env)

    await env.processor.on_message(inbound("tg", "owner", "/model some-model-from-next-year"))
    await wait_until(lambda: any("some-model-from-next-year" in t for t in adapter.texts()))

    cfg = await env.chat.get_agent_config(await env.active_conversation(resource))
    assert cfg.model == "some-model-from-next-year"
