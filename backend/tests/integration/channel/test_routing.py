"""Per-channel agent routing from chat (FR-013)."""

from __future__ import annotations

import pytest

from .conftest import ChannelEnv, inbound, wait_until

# -- /agent --------------------------------------------------------------------


async def test_agent_no_arg_lists_current_and_available(env: ChannelEnv) -> None:
    env.add_agent("codex")
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/agent"))

    [reply] = adapter.texts()
    assert "builtin" in reply  # current
    assert "codex" in reply  # available


async def test_agent_switch_opens_new_conversation_and_sticks(env: ChannelEnv) -> None:
    env.add_agent("codex", reply="codex-here")
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/agent codex"))
    await wait_until(lambda: any("codex" in t.lower() for t in adapter.texts()))

    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.preferred_agent == "codex"
    conv = await env.chat.get_conversation(peer.active_conversation_id)
    assert conv.agent_key == "codex"

    # The next message is answered by the chosen agent.
    await env.processor.on_message(inbound("tg", "owner", "hello"))
    await wait_until(lambda: "codex-here" in adapter.texts())


@pytest.mark.acceptance(spec="009-channels", scenario="/agent rejects an unknown agent")
async def test_agent_rejects_unknown_key(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/agent nope"))

    reply = adapter.texts()[-1]
    assert "nope" in reply
    assert "builtin" in reply  # lists valid keys
    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.preferred_agent is None  # unchanged


# -- /new + /status honor sticky choices ---------------------------------------


@pytest.mark.acceptance(spec="009-channels", scenario="/agent switches the agent and sticks")
async def test_new_reuses_sticky_agent(env: ChannelEnv) -> None:
    env.add_agent("codex", reply="codex-here")
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/agent codex"))
    await wait_until(lambda: adapter.texts())
    await env.processor.on_message(inbound("tg", "owner", "/new"))

    peer = await env.peers.get(resource.id)
    assert peer is not None
    conv = await env.chat.get_conversation(peer.active_conversation_id)
    assert conv.agent_key == "codex"  # /new kept the sticky agent


# -- /model (parametric: same conversation, next turn) -------------------------


# NOTE: the builtin-agent /model tests (registry override + reject-unknown) were
# removed with ADR-024 — the builtin chat agent that resolved models from the
# registry is retired. Channels route to managed agents only, whose /model is the
# raw passthrough covered by the bridged test below (which now carries the
# spec-009 "/model" acceptance marker).


@pytest.mark.acceptance(spec="009-channels", scenario="/model switches the model for the next turn")
async def test_model_switch_for_bridged_agent_passes_through_to_agent_config(
    env: ChannelEnv,
) -> None:
    env.add_agent("codex", reply="ok")
    resource, adapter = await env.paired_channel()
    await env.processor.on_message(inbound("tg", "owner", "/agent codex"))
    await wait_until(lambda: adapter.texts())

    await env.processor.on_message(inbound("tg", "owner", "/model gpt-5-codex"))
    await wait_until(lambda: any("gpt-5-codex" in t for t in adapter.texts()))

    peer = await env.peers.get(resource.id)
    assert peer is not None
    cfg = await env.chat.get_agent_config(peer.active_conversation_id)
    assert cfg.model == "gpt-5-codex"  # bridged → raw passthrough


async def test_status_reports_agent(env: ChannelEnv) -> None:
    env.add_agent("codex", reply="codex-here")
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/agent codex"))
    await wait_until(lambda: adapter.texts())
    adapter.sent.clear()
    await env.processor.on_message(inbound("tg", "owner", "/status"))

    status = adapter.texts()[-1]
    assert "codex" in status.lower()


# -- group command replies route back to the group/thread, not a DM (regression) -


@pytest.mark.acceptance(
    spec="009-channels", scenario="a group slash-command reply routes to the group/thread"
)
async def test_group_status_command_reply_routes_to_group_and_thread(env: ChannelEnv) -> None:
    """Regression: an owner's ``/status`` sent inside a group thread must have
    its reply routed with ``chat_kind="group"`` and that same ``thread_id`` —
    not fall through to the ``_safe_send`` DM defaults, which would target the
    wrong endpoint (and, on SeaTalk, get silently rejected)."""
    _resource, adapter = await env.paired_channel(sender_id="owner-1")

    await env.processor.on_message(
        inbound(
            "tg",
            "grp-1",
            "/status",
            chat_kind="group",
            addressed=True,
            sender_id="owner-1",
            thread_id="th-1",
        )
    )

    assert len(adapter.sent) == 1
    chat_id, text = adapter.sent[0]
    assert chat_id == "grp-1"
    assert "Conversation" in text
    assert adapter.sent_routed[0] == (chat_id, text, "th-1", "group")


async def test_dm_status_command_reply_still_routes_direct(env: ChannelEnv) -> None:
    """DM regression: a ``/status`` command in a DM still replies with the
    untouched defaults (``chat_kind="direct"``, ``thread_id=""``)."""
    _resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/status"))

    assert len(adapter.sent) == 1
    chat_id, text = adapter.sent[0]
    assert adapter.sent_routed[0] == (chat_id, text, "", "direct")
