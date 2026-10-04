"""``ChannelPlaces`` — where in its channel each conversation of the
Conversations list lives (spec chat "Show every conversation on the
Conversations page").

Satisfies the chat kind's ``ChannelPlacesPort``. Application layer only: no
infrastructure import here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from coffer.application.channel.store_ports import ChannelThreadConversationRepoPort
from coffer.domain.chat.channel_place import ChannelPlaceView

__all__ = ["ChannelPlaces"]


class ChannelPlaces:
    """Reads the thread history for the places of a page of conversations."""

    def __init__(self, *, threads: ChannelThreadConversationRepoPort) -> None:
        self._threads = threads

    async def places(self, conversation_ids: Sequence[str]) -> Mapping[str, ChannelPlaceView]:
        """One read for the whole page (``locate_many``). ``chat_name`` stays
        ``None``: Coffer keeps no group title — a group's peer row names the
        owner who paired it, not the group."""
        located = await self._threads.locate_many(conversation_ids)
        return {
            conversation_id: ChannelPlaceView(
                chat_kind=loc.chat_kind if loc.chat_kind in ("direct", "group") else None,
                thread=loc.thread_id != "",
                parallel_mark=row.parallel_mark if row is not None else None,
            )
            for conversation_id, (loc, row) in located.items()
        }
