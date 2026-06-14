"""Per-channel agent + workspace routing from chat (FR-013, FR-016)."""

from __future__ import annotations

import pytest

from coffer.domain.errors import ConfigValidationError, ResourceNotFound
from coffer.domain.resource import ResourceRef

from .conftest import ChannelEnv, inbound, wait_until

# -- registration validates the workspace allowlist (FR-016) -------------------


async def test_register_accepts_existing_workspace_dirs(env: ChannelEnv, tmp_path) -> None:  # type: ignore[no-untyped-def]
    ws = tmp_path / "ws"
    ws.mkdir()
    resource = await env.register_channel(
        "ok",
        config={
            "channel_type": "telegram",
            "bot_token_ref": "channel/tg/bot-token",
            "workspaces": [{"name": "w", "path": str(ws)}],
            "default_workspace": "w",
        },
    )
    assert resource.name == "ok"


async def test_register_rejects_a_nonexistent_workspace_dir(env: ChannelEnv, tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ConfigValidationError):
        await env.register_channel(
            "bad",
            config={
                "channel_type": "telegram",
                "bot_token_ref": "channel/tg/bot-token",
                "workspaces": [{"name": "w", "path": str(tmp_path / "missing")}],
            },
        )
    with pytest.raises(ResourceNotFound):
        await env.resources.get(ResourceRef(kind="channel", name="bad"))


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


# -- /cwd ----------------------------------------------------------------------


async def test_cwd_no_arg_lists_workspaces_and_current(env: ChannelEnv) -> None:
    resource = await env.register_channel("tg")
    adapter = env.bind(resource, workspaces={"proj": "/srv/proj", "docs": "/srv/docs"})
    await env.pair(resource)

    await env.processor.on_message(inbound("tg", "owner", "/cwd"))

    [reply] = adapter.texts()
    assert "proj" in reply
    assert "docs" in reply


@pytest.mark.acceptance(
    spec="009-channels", scenario="/cwd selects a configured workspace and refuses a bare path"
)
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
    assert cfg["model"] == "gpt-5-codex"  # bridged → raw passthrough


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
