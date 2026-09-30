"""`/model` — the model and its reasoning effort from a chat.

See spec channels "Switch the model and reasoning effort from chat".

One command: bare `/model` is a two-step card (model, then effort), `/model
<level>` sets the effort only, `/model <name> [<level>]` the model and
optionally the effort, `/model default` clears both. Each lands on the SAME
conversation's next turn and sticks on the thread.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from coffer.application.channel.selection_cards import is_page_turn

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


async def _config(env: ChannelEnv, resource: Resource) -> tuple[str | None, str | None]:
    cfg = await env.chat.get_agent_config(await env.active_conversation(resource))
    return cfg.model, cfg.effort


async def _sticky(env: ChannelEnv, resource: Resource) -> tuple[str | None, str | None]:
    row = await env.threads.get(resource.uid, "owner", "")
    assert row is not None
    return row.preferred_model, row.preferred_effort


@pytest.mark.acceptance(spec="channels", scenario="/model with a level sets the effort only")
async def test_a_level_sets_the_effort_only(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()
    await env.processor.on_message(inbound("tg", "owner", "/model opus"))

    await env.processor.on_message(inbound("tg", "owner", "/model xhigh"))

    assert await _config(env, resource) == ("opus", "xhigh")
    assert await _sticky(env, resource) == ("opus", "xhigh")
    assert adapter.texts()[-1] == "🎚 Effort set to xhigh for the next turn."


async def test_a_name_and_a_level_set_both(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/model gpt-5 high"))

    assert await _config(env, resource) == ("gpt-5", "high")
    assert adapter.texts() == ["🧠 Model set to gpt-5, effort high for the next turn."]


async def test_a_model_is_matched_by_its_shown_name(env: ChannelEnv) -> None:
    env.model_suggestions.add(
        "builtin", ["claude-fable-5-1[1m]"], labels={"claude-fable-5-1[1m]": "Fable 1M"}
    )
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/model fable 1m"))

    assert (await _config(env, resource))[0] == "claude-fable-5-1[1m]"
    assert adapter.texts() == ["🧠 Model set to Fable 1M for the next turn."]


async def test_an_unknown_model_passes_through_verbatim(env: ChannelEnv) -> None:
    """The agent's CLI owns the model namespace; a name Coffer does not know is
    stored and judged there, next turn."""
    resource, _adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/model something-exotic"))

    assert (await _config(env, resource))[0] == "something-exotic"


@pytest.mark.acceptance(spec="channels", scenario="/model default clears the model and effort")
async def test_default_clears_the_model_and_effort(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()
    await env.processor.on_message(inbound("tg", "owner", "/model opus high"))

    await env.processor.on_message(inbound("tg", "owner", "/model default"))

    assert await _config(env, resource) == (None, None)
    assert await _sticky(env, resource) == (None, None)
    assert "reset to the agent's defaults" in adapter.texts()[-1]


async def test_bare_model_without_buttons_answers_in_text(env: ChannelEnv) -> None:
    env.model_suggestions.add("builtin", ["opus", "sonnet"])
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/model"))

    [text] = adapter.texts()
    assert text.startswith("Model: default model\nEffort: default")
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


@pytest.mark.acceptance(spec="channels", scenario="a model tap leads to the effort step")
async def test_a_model_tap_rewrites_the_card_into_the_effort_step(env: ChannelEnv) -> None:
    env.model_suggestions.add("builtin", ["gpt-5", "gpt-4"])
    env.model_suggestions.add_efforts("builtin", ["low", "high"], model="gpt-5")
    resource, adapter = await _card_channel(env)

    await env.processor.on_callback(
        tap_event("tg", "owner", "model:gpt-5", platform_message_id="card-1")
    )

    assert (await _config(env, resource))[0] == "gpt-5"
    [(_chat, mid, text, buttons, title)] = adapter.card_updates
    assert (mid, title) == ("card-1", "Effort")
    assert "Model: gpt-5" in text
    assert [b.value for b in buttons] == ["effort:low", "effort:high", "effort:-"]
    assert buttons[-1].label == "Keep default"

    await env.processor.on_callback(
        tap_event("tg", "owner", "effort:high", platform_message_id="card-1")
    )

    assert await _config(env, resource) == ("gpt-5", "high")
    assert await _sticky(env, resource) == ("gpt-5", "high")
    _chat, _mid, _text, buttons, title = adapter.card_updates[-1]
    assert title == "Effort"
    assert [b.value for b in buttons if b.selected] == ["effort:high"]


async def test_keep_leaves_the_effort_alone(env: ChannelEnv) -> None:
    env.model_suggestions.add("builtin", ["gpt-5"])
    env.model_suggestions.add_efforts("builtin", ["low", "high"], model="gpt-5")
    resource, adapter = await _card_channel(env)
    await env.processor.on_message(inbound("tg", "owner", "/model low"))

    await env.processor.on_callback(
        tap_event("tg", "owner", "model:gpt-5", platform_message_id="card-1")
    )
    await env.processor.on_callback(
        tap_event("tg", "owner", "effort:-", platform_message_id="card-1")
    )

    assert await _config(env, resource) == ("gpt-5", "low")
    assert adapter.texts()[-1] == "🎚 Effort kept at low."
    # The card goes back to the model step with the new model ticked.
    _chat, _mid, _text, buttons, title = adapter.card_updates[-1]
    assert title == "Model"
    assert [b.value for b in buttons if b.selected] == ["model:gpt-5"]


async def test_without_card_update_the_effort_step_is_a_fresh_card(env: ChannelEnv) -> None:
    env.model_suggestions.add("builtin", ["gpt-5"])
    env.model_suggestions.add_efforts("builtin", ["low", "high"], model="gpt-5")
    _resource, adapter = await _card_channel(env, update=False)

    await env.processor.on_callback(
        tap_event("tg", "owner", "model:gpt-5", platform_message_id="card-1")
    )

    assert adapter.card_updates == []
    assert adapter.card_titles == ["Effort"]


async def test_a_model_without_levels_just_moves_the_tick(env: ChannelEnv) -> None:
    env.model_suggestions.add("builtin", ["opus", "sonnet"])
    _resource, adapter = await _card_channel(env)

    await env.processor.on_callback(
        tap_event("tg", "owner", "model:sonnet", platform_message_id="card-1")
    )

    [(_chat, _mid, _text, buttons, title)] = adapter.card_updates
    assert title == "Model"
    assert [b.value for b in buttons if b.selected] == ["model:sonnet"]


async def test_a_page_turn_on_the_effort_step_changes_nothing(env: ChannelEnv) -> None:
    """`page:effort:<n>` must reach the re-render path, not the apply path."""
    env.model_suggestions.add_efforts("builtin", [f"level-{i}" for i in range(12)])
    resource, adapter = await _card_channel(env)
    await env.processor.on_message(inbound("tg", "owner", "/new"))

    await env.processor.on_callback(
        tap_event("tg", "owner", "page:effort:1", platform_message_id="card-1")
    )

    [(_chat, _mid, text, buttons, _title)] = adapter.card_updates
    assert "Page 2/" in text
    assert any(is_page_turn(b.value) for b in buttons)
    assert await _config(env, resource) == (None, None)
    assert not any("Effort set to" in t for t in adapter.texts())


@pytest.mark.acceptance(
    spec="channels", scenario="/new keeps the chat's model, effort and directory"
)
async def test_new_keeps_the_chats_model_effort_and_directory(
    env: ChannelEnv, tmp_path: Path
) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, directories=[str(tmp_path)])
    await env.pair(resource, "owner")
    await env.processor.on_message(inbound("tg", "owner", "/model opus medium"))
    await env.processor.on_message(inbound("tg", "owner", f"/dir {tmp_path}"))
    first = await env.active_conversation(resource)

    await env.processor.on_message(inbound("tg", "owner", "/new"))

    fresh = await env.active_conversation(resource)
    assert fresh not in (None, first)
    assert await _config(env, resource) == ("opus", "medium")
    cfg = await env.chat.get_agent_config(fresh)
    assert cfg.cwd == str(tmp_path)
    assert adapter.texts()[-1] == (
        f"🆕 New conversation · Coffer Assistant · opus · Medium · {tmp_path}"
    )
