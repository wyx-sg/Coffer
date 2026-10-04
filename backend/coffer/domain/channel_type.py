"""The closed set of IM platform keys a channel can be.

One neutral home for the vocabulary the wire names (``ChannelStatusOut.channel_type``,
a conversation's ``channel_binding.platform``), so the generated contract carries the
set and the frontend does not re-declare it. The channel configs in
``coffer.domain.channel.config`` discriminate on exactly these values.
"""

from __future__ import annotations

from typing import Literal

ChannelType = Literal["telegram", "seatalk"]
