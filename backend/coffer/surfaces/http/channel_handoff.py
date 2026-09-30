"""The SeaTalk SDK hand-off, with the facts only the infrastructure knows.

``application/channel/sdk_handoff.py`` writes the prompt; where the daemon
looks for the SDK is ``infrastructure/channel/seatalk_sdk.py``'s to say. This
joins the two for the status route and the Overview's attention item, so both
hand over the same words.
"""

from __future__ import annotations

from coffer.application.channel.sdk_handoff import seatalk_sdk_handoff
from coffer.infrastructure.channel import seatalk_sdk


def sdk_missing_handoff(channel_name: str) -> str:
    return seatalk_sdk_handoff(channel_name, seatalk_sdk.sdk_location(), seatalk_sdk.DOCS_URL)


__all__ = ["sdk_missing_handoff"]
