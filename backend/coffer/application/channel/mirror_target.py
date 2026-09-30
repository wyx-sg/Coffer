"""Where a web reply on a channel's conversation would go (spec chat "Mirror a
web reply into the channel it came from").

Split out of ``mirror`` so the decision — which chat and thread, whether they
can be written to at all, and the label the Chat page shows — reads on its own:
``resolve_target`` answers it from the thread history, and ``ChannelMirror``
only acts on the answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.application.channel.store_ports import (
    ChannelThreadConversationRepoPort,
    ChannelThreadLocation,
)
from coffer.domain.errors import CofferError
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService

__all__ = ["MirrorTarget", "platform_label", "resolve_target"]

#: The prefix a reply typed on the web carries into the chat, so the chat can
#: tell it from one the owner typed there.
FROM_COFFER = "(from Coffer) "

_PLATFORMS = {"seatalk": "SeaTalk", "telegram": "Telegram"}


def platform_label(channel_type: str) -> str:
    return _PLATFORMS.get(channel_type, channel_type.title() if channel_type else "")


@dataclass(frozen=True)
class MirrorTarget:
    """The resolved destination of a mirrored reply. ``location`` is ``None``
    (and ``reason`` set) when no chat can be written to."""

    resource: Resource | None
    location: ChannelThreadLocation | None
    platform: str
    target: str
    reason: str | None

    @property
    def deliverable(self) -> bool:
        return self.reason is None


def _place(platform: str, loc: ChannelThreadLocation, mark: str | None) -> str:
    """``SeaTalk · 🧵#1 deploy check`` / ``… · direct chat`` / ``… · thread``."""
    if mark:
        where = mark
    elif loc.chat_kind == "group":
        if loc.thread_id == "":
            where = "group chat"
        else:
            where = "topic" if platform == "Telegram" else "thread"
    else:
        where = "direct chat" if loc.thread_id == "" else "thread"
    return f"{platform} · {where}" if platform else where


async def resolve_target(
    resources: ResourceService,
    threads: ChannelThreadConversationRepoPort,
    conversation_id: str,
    channel_uid: str,
) -> MirrorTarget:
    """Which chat and thread a reply on ``conversation_id`` reaches.

    Deliverable: a direct chat (any thread) and a group thread. Never a group's
    main chat — a reply there would land in front of the whole group rather
    than in the conversation it belongs to, so it stays in Coffer."""
    try:
        resource = await resources.get(channel_uid)
    except CofferError:
        return MirrorTarget(None, None, "", "", "channel_deleted")
    platform = platform_label(str(resource.config.get("channel_type", "")))
    loc = await threads.locate(conversation_id)
    if loc is None or loc.resource_uid != resource.uid:
        return MirrorTarget(resource, None, platform, platform, "not_located")
    if loc.chat_kind not in ("direct", "group"):
        return MirrorTarget(resource, None, platform, platform, "chat_kind_unknown")
    row = await threads.get(loc.resource_uid, loc.chat_id, loc.thread_id)
    label = _place(platform, loc, row.parallel_mark if row is not None else None)
    if loc.chat_kind == "group" and loc.thread_id == "":
        return MirrorTarget(resource, None, platform, label, "group_main")
    return MirrorTarget(resource, loc, platform, label, None)
