"""Per-channel agent routing from chat (spec channels "Switch the agent with /new"
and "Keep a chat's agent, model and directory across its conversations")."""

from __future__ import annotations

import pytest

from .conftest import ChannelEnv, inbound, wait_until

# -- /new <agent> --------------------------------------------------------------


@pytest.mark.acceptance(spec="channels", scenario="/new with an agent name switches and sticks")
async def test_new_with_an_agent_name_switches_and_sticks(env: ChannelEnv) -> None:
    env.add_agent("claude_code", reply="claude-here")
    resource, adapter = await env.paired_channel()
    first = None

    # Typed the way a person sees it: display name, any case, spaces.
    await env.processor.on_message(inbound("tg", "owner", "/new claude code"))

    assert await env.thread_preferred_agent(resource) == "claude_code"
    first = await env.active_conversation(resource)
    conv = await env.chat.get_conversation(first)
    assert conv.agent_key == "claude_code"
    assert adapter.texts() == [
        "🆕 New conversation · Claude_Code · Default model · Default directory"
    ]

    # It sticks: a plain /new opens another conversation on the same agent.
    await env.processor.on_message(inbound("tg", "owner", "/new"))
    second = await env.active_conversation(resource)
    assert second != first
    assert (await env.chat.get_conversation(second)).agent_key == "claude_code"

    # The next message is answered by the chosen agent.
    await env.processor.on_message(inbound("tg", "owner", "hello"))
    await wait_until(lambda: "claude-here" in adapter.texts())


async def test_the_resource_style_name_also_switches(env: ChannelEnv) -> None:
    env.add_agent("claude_code")
    resource, _adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/new claude-code"))

    assert await env.thread_preferred_agent(resource) == "claude_code"


@pytest.mark.acceptance(spec="channels", scenario="/new rejects an unknown agent name")
async def test_new_rejects_an_unknown_agent_name(env: ChannelEnv) -> None:
    env.add_agent("claude_code")
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/new nope"))

    [reply] = adapter.texts()
    assert reply == (
        "Unknown agent 'nope'. Available: Coffer Assistant (builtin), Claude_Code (claude-code)"
    )
    assert "claude_code" not in reply  # never a raw key
    assert await env.thread_preferred_agent(resource) is None  # unchanged
    assert await env.active_conversation(resource) is None  # nothing opened


async def test_switching_the_agent_drops_the_model_but_keeps_the_directory(
    env: ChannelEnv,
) -> None:
    env.add_agent("codex")
    resource, _adapter = await env.paired_channel()
    await env.processor.on_message(inbound("tg", "owner", "/model opus"))
    await env.threads.set_preferences(resource.uid, "owner", "", cwd="/src/app")

    await env.processor.on_message(inbound("tg", "owner", "/new codex"))

    row = await env.threads.get(resource.uid, "owner", "")
    assert row is not None
    assert (row.preferred_agent, row.preferred_model) == ("codex", None)
    assert row.preferred_cwd == "/src/app"


# -- /model (parametric: same conversation, next turn) -------------------------


# NOTE: the builtin-agent /model tests (registry override + reject-unknown) were
# removed — the builtin chat agent that resolved models from the
# registry is retired. Channels route to managed agents only, whose /model is the
# raw passthrough covered by the bridged test below (which now carries the
# channels "/model" acceptance marker).


@pytest.mark.acceptance(spec="channels", scenario="/model switches the model for the next turn")
async def test_model_switch_for_bridged_agent_passes_through_to_agent_config(
    env: ChannelEnv,
) -> None:
    env.add_agent("codex", reply="ok")
    resource, adapter = await env.paired_channel()
    await env.processor.on_message(inbound("tg", "owner", "/new codex"))
    await wait_until(lambda: adapter.texts())

    await env.processor.on_message(inbound("tg", "owner", "/model gpt-5-codex"))
    await wait_until(lambda: any("gpt-5-codex" in t for t in adapter.texts()))

    cfg = await env.chat.get_agent_config(await env.active_conversation(resource))
    assert cfg.model == "gpt-5-codex"  # bridged → raw passthrough


async def test_status_reports_agent(env: ChannelEnv) -> None:
    env.add_agent("codex", reply="codex-here")
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/new codex"))
    await wait_until(lambda: adapter.texts())
    adapter.sent.clear()
    await env.processor.on_message(inbound("tg", "owner", "/status"))

    status = adapter.texts()[-1]
    assert "\nCodex · Default model" in status


# -- group command replies route back to the group/thread, not a DM (regression) -


@pytest.mark.acceptance(
    spec="channels", scenario="a group slash-command reply routes to the group/thread"
)
async def test_group_help_command_reply_routes_to_group_and_thread(env: ChannelEnv) -> None:
    """Regression: an owner's ``/help`` sent inside a group thread must have
    its reply routed with ``chat_kind="group"`` and that same ``thread_id`` —
    not fall through to the ``_safe_send`` DM defaults, which would target the
    wrong endpoint (and, on SeaTalk, get silently rejected)."""
    _resource, adapter = await env.paired_channel(sender_id="owner-1")

    await env.processor.on_message(
        inbound(
            "tg",
            "grp-1",
            "/help",
            chat_kind="group",
            addressed=True,
            sender_id="owner-1",
            thread_id="th-1",
        )
    )

    assert len(adapter.sent) == 1
    chat_id, text = adapter.sent[0]
    assert chat_id == "grp-1"
    assert text.startswith("/new")
    assert adapter.sent_routed[0] == (chat_id, text, "th-1", "group")


async def test_dm_status_command_reply_still_routes_direct(env: ChannelEnv) -> None:
    """DM regression: a ``/status`` command in a DM still replies with the
    untouched defaults (``chat_kind="direct"``, ``thread_id=""``)."""
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/status"))

    assert len(adapter.sent) == 1
    chat_id, text = adapter.sent[0]
    assert adapter.sent_routed[0] == (chat_id, text, "", "direct")
