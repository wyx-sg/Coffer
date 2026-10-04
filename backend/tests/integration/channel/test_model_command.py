"""`/model` — the model from a chat.

See spec channels "Switch the model from chat".

One command: bare `/model` is a card of the agent's models, `/model <name>`
sets the model (a lone word is a model name), `/model default` clears it. Each
lands on the SAME conversation's next turn and sticks on the thread.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from .conftest import ChannelEnv, FakeChannelAdapter, Resource, inbound, tap_event


async def _card_channel(
    env: ChannelEnv, *, update: bool = True
) -> tuple[Resource, FakeChannelAdapter]:
    resource = await env.register_channel("tg")
    adapter = env.bind(
        resource, FakeChannelAdapter(supports_buttons=True, supports_card_update=update)
    )
    await env.pair(resource, "owner")
    return resource, adapter


async def _config(env: ChannelEnv, resource: Resource) -> str | None:
    cfg = await env.chat.get_agent_config(await env.active_conversation(resource))
    return cfg.model


async def _sticky(env: ChannelEnv, resource: Resource) -> str | None:
    row = await env.threads.get(resource.uid, "owner", "")
    assert row is not None
    return row.preferred_model


async def test_a_model_is_matched_by_its_shown_name(env: ChannelEnv) -> None:
    env.model_suggestions.add(
        "builtin", ["claude-fable-5-1[1m]"], labels={"claude-fable-5-1[1m]": "Fable 1M"}
    )
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/model fable 1m"))

    assert await _config(env, resource) == "claude-fable-5-1[1m]"
    assert adapter.texts() == ["Model: Fable 1M — from your next message"]


async def test_an_unknown_model_passes_through_verbatim(env: ChannelEnv) -> None:
    """The agent's CLI owns the model namespace; a name Coffer does not know is
    stored and judged there, next turn."""
    resource, _adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/model something-exotic"))

    assert await _config(env, resource) == "something-exotic"


async def test_a_lone_word_is_a_model_name(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/model high"))

    assert await _config(env, resource) == "high"
    assert await _sticky(env, resource) == "high"
    assert adapter.texts() == ["Model: high — from your next message"]


@pytest.mark.acceptance(spec="channels", scenario="/model default clears the model")
async def test_default_clears_the_model(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()
    await env.processor.on_message(inbound("tg", "owner", "/model opus"))

    await env.processor.on_message(inbound("tg", "owner", "/model default"))

    assert await _config(env, resource) is None
    assert await _sticky(env, resource) is None
    assert adapter.texts()[-1] == "Model: the agent's default — from your next message"


async def test_bare_model_without_buttons_answers_in_text(env: ChannelEnv) -> None:
    env.model_suggestions.add("builtin", ["opus", "sonnet"])
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/model"))

    [text] = adapter.texts()
    assert text.startswith("Model: default model")
    assert "Available: opus, sonnet" in text


@pytest.mark.acceptance(spec="channels", scenario="a model card button shows the model's name")
async def test_a_model_card_button_shows_the_models_name(env: ChannelEnv) -> None:
    env.model_suggestions.add(
        "builtin", ["fable", "claude-fable-5-1[1m]"], labels={"claude-fable-5-1[1m]": "Fable 1M"}
    )
    _resource, adapter = await _card_channel(env)

    await env.processor.on_message(inbound("tg", "owner", "/model"))

    [(_chat, _text, buttons)] = adapter.cards
    assert [(b.label, b.value) for b in buttons] == [
        ("fable", "model:fable"),
        ("Fable 1M", "model:claude-fable-5-1[1m]"),
    ]


async def test_a_model_tap_sets_it_and_moves_the_tick(env: ChannelEnv) -> None:
    env.model_suggestions.add("builtin", ["opus", "sonnet"])
    _resource, adapter = await _card_channel(env)

    await env.processor.on_callback(
        tap_event("tg", "owner", "model:sonnet", platform_message_id="card-1")
    )

    [(_chat, _mid, _text, buttons, title)] = adapter.card_updates
    assert title == "Model"
    assert [b.value for b in buttons if b.selected] == ["model:sonnet"]


@pytest.mark.acceptance(spec="channels", scenario="/new keeps the chat's model and directory")
async def test_new_keeps_the_chats_model_and_directory(env: ChannelEnv, tmp_path: Path) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, directories=[str(tmp_path)])
    await env.pair(resource, "owner")
    await env.processor.on_message(inbound("tg", "owner", "/model opus"))
    await env.processor.on_message(inbound("tg", "owner", f"/dir {tmp_path}"))
    first = await env.active_conversation(resource)

    await env.processor.on_message(inbound("tg", "owner", "/new"))

    fresh = await env.active_conversation(resource)
    assert fresh not in (None, first)
    assert await _config(env, resource) == "opus"
    cfg = await env.chat.get_agent_config(fresh)
    assert cfg.cwd == str(tmp_path)
    assert adapter.texts()[-1] == (f"🆕 New conversation · Coffer Assistant · opus · {tmp_path}")
