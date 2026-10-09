"""The facts a channel-driven turn's system note is written from (spec channels
"Tell a channel-driven agent it is on a chat channel").

Chat composes the note; this reads what only the channel kind knows — which
platform, whether the conversation is a direct chat or a group thread, and what
Markdown the running transport renders — and hands it over as the domain value
``ChannelNote``. Application layer only: no infrastructure import here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from coffer.application.channel.ports import ChannelBinding
from coffer.application.channel.store_ports import ChannelThreadConversationRepoPort
from coffer.domain.chat.channel_note import ChannelNote
from coffer.domain.errors import CofferError

if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService

__all__ = ["ChannelNoteReader", "owner_prompt", "platform_label"]

_PLATFORMS = {"seatalk": "SeaTalk", "telegram": "Telegram"}


def platform_label(channel_type: str) -> str:
    return _PLATFORMS.get(channel_type, channel_type.title() if channel_type else "")


#: Which stored prompt a chat kind reads (spec channels "Append the owner's system
#: prompt to a channel turn"). A thread takes its chat's: a group thread the
#: group prompt, a direct-chat thread the direct one.
_PROMPT_KEYS = {"direct": "direct_system_prompt", "group": "group_system_prompt"}


def owner_prompt(config: Mapping[str, object], chat_kind: str) -> str:
    """The channel's own system prompt for ``chat_kind``, or "" — when none is
    set, or when the conversation's chat kind is unknown (no prompt is guessed)."""
    key = _PROMPT_KEYS.get(chat_kind)
    value = config.get(key) if key else None
    return value.strip() if isinstance(value, str) else ""


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
        binding = self._binding(resource.uid)
        chat_kind = (loc.chat_kind or "") if loc is not None else ""
        # Read from the stored config on every turn, not from the binding the
        # adapter started with: an edited prompt applies from the next turn, with
        # no restart.
        return ChannelNote(
            name=resource.name,
            platform=platform,
            chat_kind=chat_kind,
            owner_prompt=owner_prompt(resource.config, chat_kind),
            in_thread=bool(loc is not None and loc.thread_id),
            renders=binding.adapter.capabilities.render_notes if binding is not None else "",
            collapses_details=(
                binding.adapter.capabilities.collapses_details if binding is not None else False
            ),
            reads_threads=binding is not None
            and binding.adapter.capabilities.supports_history_fetch,
        )
