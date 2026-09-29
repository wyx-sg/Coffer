"""The facts a channel-driven turn's system note is written from (spec channels
"Tell a channel-driven agent it is on a chat channel").

Chat composes the note; this reads what only the channel kind knows — which
platform, whether the conversation is a direct chat or a group thread, and what
Markdown the running transport renders — and hands it over as the domain value
``ChannelNote``. Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from coffer.application.channel.mirror_target import platform_label
from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.store_ports import ChannelThreadConversationRepoPort
from coffer.domain.chat.channel_note import ChannelNote
from coffer.domain.errors import CofferError

if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService

__all__ = ["ChannelNoteReader"]


class ChannelNoteReader:
    """``await reader(channel_uid, conversation_id)`` → the note's facts."""

    def __init__(
        self,
        *,
        resources: ResourceService,
        threads: ChannelThreadConversationRepoPort,
        binding: Callable[[str], ChannelBinding | None],
    ) -> None:
        self._resources = resources
        self._threads = threads
        self._binding = binding

    async def __call__(self, channel_uid: str, conversation_id: str) -> ChannelNote | None:
        try:
            resource = await self._resources.get(channel_uid)
        except CofferError:
            return None  # deleted: the turn is still a channel turn, with no facts left
        platform = platform_label(str(resource.config.get("channel_type", "")))
        loc = await self._threads.locate(conversation_id)
        binding = self._binding(resource.name)
        return ChannelNote(
            name=resource.name,
            platform=platform,
            chat_kind=(loc.chat_kind or "") if loc is not None else "",
            in_thread=bool(loc is not None and loc.thread_id),
            renders=binding.adapter.capabilities.render_notes if binding is not None else "",
        )
