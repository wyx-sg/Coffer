"""``coffer__channel_read_thread``: an agent reads a thread's earlier messages
page by page (spec channels "Read a thread's earlier messages on demand")."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.thread_tool import ThreadReader, channel_read_thread_tool
from coffer.domain.channel.envelopes import InboundAttachment
from coffer.domain.channel.rich_content import ForwardedItem
from coffer.domain.channel.thread_messages import ThreadMessage

from .conftest import ChannelEnv, FakeChannelAdapter

_T0 = datetime(2026, 10, 1, tzinfo=UTC)


def _message(n: int) -> ThreadMessage:
    return ThreadMessage(
        message_id=f"m-{n}",
        sender="alice@x.com",
        sent_at=_T0 + timedelta(minutes=n),
        items=(ForwardedItem(sender="alice@x.com", text=f"message {n}"),),
        has_media=n == 3,
    )


async def _reader(env: ChannelEnv, adapter: FakeChannelAdapter, name: str = "st") -> ThreadReader:
    resource = await env.register_channel(name)
    env.bind(resource, adapter)
    await env.pair(resource, "owner", sender_id="owner-1")
    await env.pair(resource, "grp-1", sender_id="owner-1")

    async def resolve(ref: str) -> ChannelBinding | None:
        return env.processor.binding(resource.uid) if ref in (name, resource.uid) else None

    return ThreadReader(resolve=resolve, peers=env.peers)


def _args(**overrides: Any) -> dict[str, Any]:
    return {
        "channel": "st",
        "chat_id": "grp-1",
        "chat_kind": "group",
        "thread_id": "th-1",
        **overrides,
    }


@pytest.mark.acceptance(
    spec="channels", scenario="an agent pages back through a thread with the tool"
)
async def test_pages_run_newest_first_with_files(env: ChannelEnv, tmp_path: Any) -> None:
    adapter = FakeChannelAdapter(supports_history_fetch=True)
    adapter.thread_messages = [_message(n) for n in range(8)]
    adapter.thread_window_note = "SeaTalk returns only the last 7 days of a thread's replies."
    picture = tmp_path / "p.png"
    picture.write_bytes(b"x")
    adapter.thread_media = {
        "m-3": (InboundAttachment(path=str(picture), mime="image/png", filename="p.png"),)
    }
    reader = await _reader(env, adapter)

    newest = await reader.read(_args(limit=3))
    assert [m["message_id"] for m in newest["messages"]] == ["m-5", "m-6", "m-7"]
    assert newest["has_more"] is True and newest["next_before"] == "m-5"
    assert newest["messages"][0]["sender"] == "alice@x.com"
    assert newest["messages"][0]["text"] == "message 5"
    assert newest["messages"][0]["sent_at"] == (_T0 + timedelta(minutes=5)).isoformat()
    assert "7 days" in newest["note"]

    older = await reader.read(_args(limit=3, before="m-5"))
    assert [m["message_id"] for m in older["messages"]] == ["m-2", "m-3", "m-4"]
    assert older["messages"][1]["files"] == [
        {"path": str(picture), "mime": "image/png", "filename": "p.png"}
    ]
    assert adapter.media_downloads == ["m-3"]

    oldest = await reader.read(_args(before="m-2"))
    assert [m["message_id"] for m in oldest["messages"]] == ["m-0", "m-1"]
    assert oldest["has_more"] is False and oldest["next_before"] is None
    assert adapter.fetch_thread_kinds == ["group", "group", "group"]


async def test_the_default_page_is_twenty_and_at_most_a_hundred(env: ChannelEnv) -> None:
    adapter = FakeChannelAdapter(supports_history_fetch=True)
    adapter.thread_messages = [_message(n) for n in range(130)]
    reader = await _reader(env, adapter)

    assert len((await reader.read(_args()))["messages"]) == 20
    assert len((await reader.read(_args(limit=500)))["messages"]) == 100
    with pytest.raises(ValueError, match="limit"):
        await reader.read(_args(limit=0))


@pytest.mark.acceptance(spec="channels", scenario="the tool reads only threads of paired chats")
async def test_an_unpaired_chat_is_refused(env: ChannelEnv) -> None:
    adapter = FakeChannelAdapter(supports_history_fetch=True)
    reader = await _reader(env, adapter)

    with pytest.raises(ValueError, match="not paired"):
        await reader.read(_args(chat_id="someone-elses-group"))
    with pytest.raises(ValueError, match="thread_id"):
        await reader.read(_args(thread_id=""))
    with pytest.raises(ValueError, match="No running channel"):
        await reader.read(_args(channel="nope"))
    assert adapter.fetch_thread_calls == []


@pytest.mark.acceptance(
    spec="channels", scenario="the tool says a platform without a history API cannot be read"
)
async def test_a_platform_without_history_says_so(env: ChannelEnv) -> None:
    adapter = FakeChannelAdapter(supports_history_fetch=False)
    reader = await _reader(env, adapter, name="tg")

    with pytest.raises(ValueError, match="has no history API"):
        await reader.read(_args(channel="tg"))
    assert adapter.fetch_thread_calls == []


async def test_a_failed_read_and_an_unknown_cursor_are_errors(env: ChannelEnv) -> None:
    adapter = FakeChannelAdapter(supports_history_fetch=True)
    adapter.thread_messages = [_message(0)]
    reader = await _reader(env, adapter)

    with pytest.raises(ValueError, match="No message"):
        await reader.read(_args(before="m-404"))
    adapter.thread_read_fails = True
    with pytest.raises(ValueError, match="did not return this thread"):
        await reader.read(_args())


@pytest.mark.acceptance(spec="channels", scenario="the tool is offered only inside a Coffer turn")
async def test_the_tool_is_turn_scoped(env: ChannelEnv) -> None:
    reader = await _reader(env, FakeChannelAdapter(supports_history_fetch=True))
    registry = BuiltinToolRegistry()
    registry.register(channel_read_thread_tool(reader))

    assert registry.list() == []
    assert registry.get("coffer__channel_read_thread") is None
    in_turn = registry.view(in_turn=True)
    assert [t.name for t in in_turn.list()] == ["channel_read_thread"]
    assert in_turn.is_builtin("coffer__channel_read_thread")
