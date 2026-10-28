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
from coffer.domain.channel.config import parse_channel_config
from coffer.domain.channel.envelopes import ChannelCapabilities
from coffer.domain.chat.channel_note import ChannelNote
from coffer.domain.errors import CofferError
from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.resource_service import ResourceService

__all__ = ["ChannelNoteReader", "platform_label", "reply_style"]

_PLATFORMS = {"seatalk": "SeaTalk", "telegram": "Telegram"}


def platform_label(channel_type: str) -> str:
    return _PLATFORMS.get(channel_type, channel_type.title() if channel_type else "")


#: Which stored reply style a chat kind reads (spec channels "Let the owner
#: rewrite a channel's reply style"). A thread takes its chat's: a group thread
#: the group style, a direct-chat thread the direct one.
_STYLE_KEYS = {"direct": "direct_reply_style", "group": "group_reply_style"}


def reply_style(config: Mapping[str, object], chat_kind: str) -> str:
    """The owner's rewrite of the reply style for ``chat_kind``, or "" — when it
    follows Coffer's default, or when the conversation's chat kind is unknown
    (the default then applies; no rewrite is guessed)."""
    key = _STYLE_KEYS.get(chat_kind)
    if key is None:
        return ""
    # Read through the typed config, not the raw document: a channel stored
    # before the reply style existed still carries the owner prompt it
    # migrates from.
    try:
        parsed = parse_channel_config(dict(config))
    except ValueError:  # pydantic's ValidationError is one
        return ""
    return str(getattr(parsed, key, "") or "")


class ChannelNoteReader:
    """``await reader(channel_uid, conversation_id)`` → the note's facts."""

    def __init__(
        self,
        *,
        resources: ResourceService,
        threads: ChannelThreadConversationRepoPort,
        binding: Callable[[str], ChannelBinding | None],
        idle_capabilities: Callable[[str], ChannelCapabilities | None] | None = None,
    ) -> None:
        self._resources = resources
        self._threads = threads
        self._binding = binding
        #: channel type -> what its transport declares when it runs. Only the
        #: page's preview reads it, so a stopped channel still shows the note
        #: it will send; a turn always reads the running transport.
        self._idle_capabilities = idle_capabilities

    async def __call__(self, channel_uid: str, conversation_id: str) -> ChannelNote | None:
        try:
            resource = await self._resources.get(channel_uid)
        except CofferError:
            return None  # deleted: the turn is still a channel turn, with no facts left
        loc = await self._threads.locate(conversation_id)
        binding = self._binding(resource.uid)
        chat_kind = (loc.chat_kind or "") if loc is not None else ""
        # Read from the stored config on every turn, not from the binding the
        # adapter started with: an edited style applies from the next turn, with
        # no restart.
        return _note(
            resource,
            chat_kind,
            in_thread=bool(loc is not None and loc.thread_id),
            caps=binding.adapter.capabilities if binding is not None else None,
        )

    async def preview(self, channel_uid: str) -> dict[str, ChannelNote]:
        """The note a direct chat and a group's main chat of this channel get,
        keyed by chat kind — what the Channels page shows (spec channels "Let
        the owner rewrite a channel's reply style")."""
        resource = await self._resources.get(channel_uid)
        binding = self._binding(resource.uid)
        caps = binding.adapter.capabilities if binding is not None else None
        if caps is None and self._idle_capabilities is not None:
            caps = self._idle_capabilities(str(resource.config.get("channel_type", "")))
        return {kind: _note(resource, kind, in_thread=False, caps=caps) for kind in _STYLE_KEYS}


def _note(
    resource: Resource, chat_kind: str, *, in_thread: bool, caps: ChannelCapabilities | None
) -> ChannelNote:
    return ChannelNote(
        name=resource.name,
        platform=platform_label(str(resource.config.get("channel_type", ""))),
        chat_kind=chat_kind,
        reply_style=reply_style(resource.config, chat_kind),
        in_thread=in_thread,
        renders=caps.render_notes if caps is not None else "",
        collapses_details=caps.collapses_details if caps is not None else False,
        reads_threads=caps is not None and caps.supports_history_fetch,
        others_can_ask=chat_kind == "group" and _others_can_ask(resource.config),
    )


def _others_can_ask(config: Mapping[str, object]) -> bool:
    try:
        return bool(parse_channel_config(dict(config)).others_can_ask)
    except ValueError:  # pydantic's ValidationError is one
        return False
