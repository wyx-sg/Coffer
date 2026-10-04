"""How a conversation row is shown beyond its columns: the channel binding.

Shared by the Conversations routes and by the composition root's bridge that
shows the same binding on an agent's Sessions tab (spec agent-registry "List an
agent's native sessions through the agent").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from coffer.application.chat.ports import ChannelPlacesPort
from coffer.application.resource_service import ResourceService
from coffer.domain.chat.channel_place import ChannelPlaceView
from coffer.domain.chat.conversation import Conversation
from coffer.surfaces.http.chat.schemas import ChannelBindingOut, ChannelPlaceOut


@dataclass(frozen=True)
class Channel:
    name: str
    #: The channel's type key (``seatalk`` / ``telegram``), or None if unset.
    platform: str | None


@dataclass(frozen=True)
class Extras:
    """What a page of conversations is rendered with beyond its rows, read in a
    CONSTANT number of queries whatever the page size: the channels once, the
    places of the channel-bound ones once. A read per row would be the N+1 the
    resource list was ordered to avoid."""

    channels: Mapping[str, Channel]
    places: Mapping[str, ChannelPlaceView]


async def conversation_extras(
    convs: Sequence[Conversation],
    resources: ResourceService,
    places_port: ChannelPlacesPort | None,
) -> Extras:
    channels = {
        c.uid: Channel(c.name, str(c.config.get("channel_type") or "") or None)
        for c in await resources.list(kind="channel")
    }
    bound = [c.id for c in convs if c.channel_uid is not None]
    places = await places_port.places(bound) if places_port is not None and bound else {}
    return Extras(channels, places)


def place_out(view: ChannelPlaceView) -> ChannelPlaceOut:
    return ChannelPlaceOut(
        chat_kind=view.chat_kind,  # type: ignore[arg-type]
        thread=view.thread,
        parallel_mark=view.parallel_mark,
        chat_name=view.chat_name,
    )


def channel_binding(conv: Conversation, extras: Extras) -> ChannelBindingOut | None:
    """The channel binding of a conversation, or None when it has none.

    A conversation "has a channel binding" iff channel_uid is set. The row stores
    the channel's IDENTITY so a renamed channel keeps its conversations; the NAME
    is resolved here, where a human reads it.
    """
    if conv.channel_uid is None:
        return None
    channel = extras.channels.get(conv.channel_uid)
    place = extras.places.get(conv.id)
    return ChannelBindingOut(
        channel_uid=conv.channel_uid,
        channel=channel.name if channel is not None else None,
        chat_id=conv.peer_chat_id or "",
        platform=channel.platform if channel is not None else None,  # type: ignore[arg-type]
        place=place_out(place) if place is not None else None,
    )


__all__ = ["Channel", "Extras", "channel_binding", "conversation_extras", "place_out"]
