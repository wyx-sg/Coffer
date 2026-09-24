"""How a SeaTalk channel's inbound is doing.

``ChannelService`` answers everything a surface asks *about* a channel — its
pairing code, its status, a notification to push. This module answers the one
question that is about the road into it: the state of the one outbound
websocket connection every SeaTalk event arrives on (spec channels/seatalk
"Report the websocket connection as the channel's inbound state").

A sibling ops module in the house style (``resource_scope_ops`` and friends):
a free function over the resource row, given the collaborator it needs, so the
service stays the surface's entry point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.domain.resource import Resource

if TYPE_CHECKING:
    from coffer.application.channel.runtime import ChannelRuntime


@dataclass(frozen=True)
class InboundInfo:
    """The state of a SeaTalk channel's websocket connection.

    There is no listener, port, path, public URL or tunnel to report — none
    exists — so the connection state is the whole health answer.
    """

    # connecting | connected | kicked | sdk_missing | error — None before the
    # first connection attempt (and on a channel that is not running at all).
    websocket_state: str | None = None
    # The last thing that went wrong on the connection, verbatim, because the
    # two failures that matter (no SDK, another process holds the connection)
    # are only actionable if the owner can read them.
    websocket_error: str | None = None


def inbound_info(resource: Resource, *, runtime: ChannelRuntime) -> InboundInfo:
    """The inbound block for a SeaTalk channel."""
    state = runtime.websocket_state(resource.uid)
    return InboundInfo(
        websocket_state=state[0] if state is not None else None,
        websocket_error=state[1] if state is not None else None,
    )
