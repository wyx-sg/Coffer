"""The built-in tool ``coffer__channel_notify``: an agent sends the channel's
owner a message, and files, in their direct chat (spec channels "Let an agent
message the owner's direct chat").

A turn Coffer runs replies on its own; this is for everything else — an agent
in a terminal, or in the agent's own scheduled task, telling the person on their
phone that it is done. It never reaches a group: the target is always the
owner's direct chat, the same chat ``POST /channels/{uid}/notify`` picks by
default. It is not turn-scoped, because the agents that need it run outside
Coffer's turns. Application layer only; the composition root registers it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from coffer.application.builtin_tools import BuiltinTool
from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.store_ports import ChannelPeerRepoPort
from coffer.application.channel.turn_media import MediaFile, local_files, send_media_files

__all__ = ["MAX_FILES", "MAX_TEXT", "OwnerNotifier", "channel_notify_tool"]

MAX_TEXT = 4000
MAX_FILES = 10

_DESCRIPTION = (
    "Send the person a message on their phone, in their direct chat with a Coffer "
    "chat channel (Telegram or SeaTalk), for example to say a long task is done. "
    "Optionally attach local files by absolute path. Pass `channel` (its name or id) "
    "when the person has more than one channel. Never posts to a group. Do not use it "
    "to answer a message that came from a chat channel: that reply is sent for you."
)

_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": f"The message, plain text, up to {MAX_TEXT} characters.",
        },
        "channel": {
            "type": "string",
            "description": "The channel's name or id. Omit when only one channel is paired.",
        },
        "files": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": MAX_FILES,
            "description": "Absolute paths of local files to send after the message.",
        },
    },
    "required": ["text"],
}

#: The running bindings of every channel, in a stable order.
ListBindings = Callable[[], Awaitable[list[ChannelBinding]]]


def _text(args: dict[str, Any]) -> str:
    text = args.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("`text` is required.")
    if len(text) > MAX_TEXT:
        raise ValueError(f"`text` is {len(text)} characters; keep it to {MAX_TEXT}.")
    return text.strip()


def _files(args: dict[str, Any]) -> tuple[MediaFile, ...]:
    raw = args.get("files") or []
    if not isinstance(raw, list) or not all(isinstance(p, str) for p in raw):
        raise ValueError("`files` must be a list of absolute paths.")
    if len(raw) > MAX_FILES:
        raise ValueError(f"Send at most {MAX_FILES} files at once.")
    return local_files(raw)


class OwnerNotifier:
    """Serves ``coffer__channel_notify``."""

    def __init__(self, *, bindings: ListBindings, peers: ChannelPeerRepoPort) -> None:
        self._bindings = bindings
        self._peers = peers

    async def _target(self, ref: str | None) -> tuple[ChannelBinding, str]:
        """The channel to use and its owner's direct chat id."""
        paired = []
        for binding in await self._bindings():
            if ref is not None and ref not in (binding.resource.uid, binding.resource.name):
                continue
            peer = await self._peers.owner_peer(binding.resource.uid)
            if peer is not None:
                paired.append((binding, peer.chat_id))
        if ref is not None and not paired:
            raise ValueError(f"No running, paired channel named {ref!r}.")
        if not paired:
            raise ValueError(
                "No chat channel is running and paired; the person has to set one up "
                "on Coffer's Channels page first."
            )
        if len(paired) > 1:
            names = ", ".join(b.resource.name for b, _ in paired)
            raise ValueError(f"Several channels are paired ({names}); pass `channel`.")
        return paired[0]

    async def notify(self, args: dict[str, Any]) -> dict[str, Any]:
        text = _text(args)
        files = _files(args)
        ref = args.get("channel")
        if ref is not None and (not isinstance(ref, str) or not ref.strip()):
            raise ValueError("`channel` must be a channel's name or id.")
        binding, chat_id = await self._target(ref.strip() if isinstance(ref, str) else None)
        adapter = binding.adapter
        await adapter.send_text(chat_id, text)
        failed: tuple[MediaFile, ...] = ()
        if files:
            if not adapter.capabilities.supports_media:
                raise ValueError(f"The {binding.resource.name} channel cannot send files.")
            failed = await send_media_files(adapter, chat_id, files)
        result: dict[str, Any] = {"sent": True, "channel": binding.resource.name}
        if failed:
            result["files_failed"] = [f.path for f in failed]
        return result


def channel_notify_tool(notifier: OwnerNotifier) -> BuiltinTool:
    """The registry entry. Not turn-scoped: the agents that need it run in a
    terminal or in their own scheduled tasks, outside any turn Coffer runs."""
    return BuiltinTool(
        name="channel_notify",
        description=_DESCRIPTION,
        input_schema=_INPUT_SCHEMA,
        handler=notifier.notify,
    )
