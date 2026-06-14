"""Per-channel agent + workspace routing from chat (FR-013, FR-016)."""

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


async def test_agent_rejects_unknown_key(env: ChannelEnv) -> None:
    resource, adapter = await env.paired_channel()

    await env.processor.on_message(inbound("tg", "owner", "/agent nope"))

    reply = adapter.texts()[-1]
    assert "nope" in reply
    assert "builtin" in reply  # lists valid keys
    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.preferred_agent is None  # unchanged


# -- /cwd ----------------------------------------------------------------------


async def test_cwd_no_arg_lists_workspaces_and_current(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, workspaces={"proj": "/srv/proj", "docs": "/srv/docs"})
    await env.pair(resource)

    await env.processor.on_message(inbound("tg", "owner", "/cwd"))

    [reply] = adapter.texts()
    assert "proj" in reply
    assert "docs" in reply


async def test_cwd_selects_workspace_and_injects_cwd(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, workspaces={"proj": "/srv/proj"})
    await env.pair(resource)

    await env.processor.on_message(inbound("tg", "owner", "/cwd proj"))
    await wait_until(lambda: adapter.texts())

    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.preferred_workspace == "proj"
    # The default (builtin) provider received the workspace path as cwd.
    assert env.provider.last_agent_config == {"cwd": "/srv/proj"}


async def test_cwd_refuses_a_bare_path(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, workspaces={"proj": "/srv/proj"})
    await env.pair(resource)

    await env.processor.on_message(inbound("tg", "owner", "/cwd /etc"))

    reply = adapter.texts()[-1]
    assert "/etc" in reply or "unknown" in reply.lower()
    peer = await env.peers.get(resource.id)
    assert peer is not None
    assert peer.preferred_workspace is None  # not set
    assert await env.chat.list_conversations() == []  # no conversation created


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


async def test_status_reports_agent_and_workspace(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, workspaces={"proj": "/srv/proj"})
    await env.pair(resource)

    await env.processor.on_message(inbound("tg", "owner", "/cwd proj"))
    await wait_until(lambda: adapter.texts())
    adapter.sent.clear()
    await env.processor.on_message(inbound("tg", "owner", "/status"))

    status = adapter.texts()[-1]
    assert "Workspace: proj" in status
