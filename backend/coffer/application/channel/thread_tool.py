"""The built-in tool ``coffer__channel_read_thread``: an agent reads a thread's
earlier messages page by page (spec channels "Read a thread's earlier messages
on demand").

A thread turn folds in only a bounded slice of its thread (``turn_context``);
this is how the agent reaches the rest when it needs it. It reads only through a
running channel's own transport, only a thread of a chat that channel has paired
(the owner's direct chat, or a group the owner has addressed the bot in), and
never a chat's main history: a thread id is required, and the transport has no
read for anything else.

It is turn-scoped, like ``coffer__ask``: listed to and served for only an MCP
session inside a turn Coffer runs, so an agent started in a terminal never sees
it. Application layer only; the composition root registers it in the
``BuiltinToolRegistry``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, cast

from coffer.application.builtin_tools import BuiltinTool
from coffer.application.channel.ports import ChannelBinding, ContextFetchPort
from coffer.application.channel.prompt_note import platform_label
from coffer.application.channel.store_ports import ChannelPeerRepoPort
from coffer.domain.channel.thread_messages import ThreadMessage

__all__ = [
    "DEFAULT_PAGE",
    "MAX_PAGE",
    "TOOL_NAME",
    "ThreadReader",
    "channel_read_thread_tool",
]

TOOL_NAME = "channel_read_thread"
DEFAULT_PAGE = 20
MAX_PAGE = 100

_DESCRIPTION = (
    "Read earlier messages of a chat thread the current channel turn came from "
    "(newest page first). Pass the channel, chat_id, chat_kind and thread_id from "
    "the turn's [Message origin] block; pass `before` (a message_id, e.g. the "
    "next_before of the previous page or the id a thread note names) to page back. "
    "Returns each message's sender, time and text, and local paths of the images "
    "and files it carries. Only threads of chats paired with Coffer can be read."
)

_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "channel": {
            "type": "string",
            "description": "The channel's name (the origin block's `channel:` line).",
        },
        "chat_id": {"type": "string", "description": "The chat id from the origin block."},
        "chat_kind": {
            "type": "string",
            "enum": ["direct", "group"],
            "description": "The chat's kind from the origin block.",
        },
        "thread_id": {"type": "string", "description": "The thread id from the origin block."},
        "before": {
            "type": "string",
            "description": "Return messages older than this message_id. Omit for the newest.",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": MAX_PAGE,
            "default": DEFAULT_PAGE,
            "description": f"Messages per page (1-{MAX_PAGE}).",
        },
    },
    "required": ["channel", "chat_id", "chat_kind", "thread_id"],
}

#: Resolves a channel's name (or uid) to its running binding, or ``None``.
ResolveBinding = Callable[[str], Awaitable[ChannelBinding | None]]


def _required(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"`{key}` is required: copy it from the turn's [Message origin] block.")
    return value.strip()


def _limit(args: dict[str, Any]) -> int:
    value = args.get("limit", DEFAULT_PAGE)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"`limit` must be an integer from 1 to {MAX_PAGE}.")
    return min(value, MAX_PAGE)


def _text(message: ThreadMessage) -> str:
    return "\n".join(
        item.text if item.sender == message.sender else f"{item.sender}: {item.text}"
        for item in message.items
    )


class ThreadReader:
    """Serves ``coffer__channel_read_thread``."""

    def __init__(self, *, resolve: ResolveBinding, peers: ChannelPeerRepoPort) -> None:
        self._resolve = resolve
        self._peers = peers

    async def read(self, args: dict[str, Any]) -> dict[str, Any]:
        channel = _required(args, "channel")
        chat_id = _required(args, "chat_id")
        thread_id = _required(args, "thread_id")
        chat_kind = _required(args, "chat_kind")
        if chat_kind not in ("direct", "group"):
            raise ValueError("`chat_kind` must be `direct` or `group`.")
        before = args.get("before")
        if before is not None and not isinstance(before, str):
            raise ValueError("`before` must be a message_id string.")
        limit = _limit(args)
        binding = await self._resolve(channel)
        if binding is None:
            raise ValueError(f"No running channel named {channel!r}.")
        if not binding.adapter.capabilities.supports_history_fetch:
            platform = platform_label(binding.channel_type)
            raise ValueError(
                f"{platform} has no history API: Coffer cannot read a thread's earlier "
                "messages there. Ask the person to paste or forward what you need."
            )
        if await self._peers.get_by_chat(binding.resource.uid, chat_id) is None:
            raise ValueError(
                f"Chat {chat_id!r} is not paired with the {binding.resource.name} channel; "
                "only threads of chats the owner uses with the bot can be read."
            )
        fetcher = cast(ContextFetchPort, binding.adapter)
        read = await fetcher.fetch_thread(chat_id, thread_id, chat_kind=chat_kind)
        if read.failed:
            raise ValueError(
                "The platform did not return this thread; check the chat_id, chat_kind "
                "and thread_id against the origin block."
            )
        messages = list(read.messages)
        if before:
            ids = [m.message_id for m in messages]
            if before not in ids:
                raise ValueError(f"No message {before!r} in this thread.")
            messages = messages[: ids.index(before)]
        page = messages[-limit:]
        more = len(messages) > len(page)
        out = []
        for message in page:
            files = await fetcher.fetch_message_media(message) if message.has_media else ()
            out.append(
                {
                    "message_id": message.message_id,
                    "sender": message.sender,
                    "sent_at": message.sent_at.isoformat() if message.sent_at else None,
                    "from_bot": message.from_bot,
                    "text": _text(message),
                    "files": [
                        {"path": f.path, "mime": f.mime, "filename": f.filename} for f in files
                    ],
                }
            )
        result: dict[str, Any] = {
            "messages": out,
            "has_more": more,
            "next_before": page[0].message_id if more and page else None,
        }
        if read.window_note:
            result["note"] = read.window_note
        return result


def channel_read_thread_tool(reader: ThreadReader) -> BuiltinTool:
    """The registry entry. Turn-scoped: offered only to an agent inside a turn
    Coffer runs, which is where a thread turn's agent is. Channels are no
    experimental feature, so no feature gates it."""
    return BuiltinTool(
        name="channel_read_thread",
        description=_DESCRIPTION,
        input_schema=_INPUT_SCHEMA,
        handler=reader.read,
        turn_scoped=True,
    )
