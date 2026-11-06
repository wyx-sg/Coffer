"""Whether an MCP session belongs to a turn Coffer is running, and the port the
gateway asks it through.

Kind-agnostic on purpose: the MCP gateway offers its turn-scoped built-in tools
(``coffer__channel_read_thread``) only to a session whose requests carry the
``X-Coffer-Turn`` token of a turn Coffer is running, but it must not import the
chat kind that runs turns. The chat kind satisfies :class:`TurnLivePort`; the
composition root hands it to the gateway.
"""

from __future__ import annotations

from typing import Protocol

from coffer.domain.channel_turn import TURN_HEADER, TURN_TOKEN_ENV


class TurnLivePort(Protocol):
    """What the gateway needs from the kind that runs turns."""

    def is_live(self, token: str | None) -> bool:
        """Whether ``token`` names a turn that is running now."""
        ...


_current: TurnLivePort | None = None


def set_turn_live(port: TurnLivePort | None) -> None:
    """Called by the composition root with the chat kind's port (``None`` unwires)."""
    global _current
    _current = port


def turn_is_live(port: TurnLivePort | None, token: str | None) -> bool:
    """Whether ``token`` names a turn Coffer is running now; ``port`` defaults to
    the wired one."""
    port = port or _current
    return port is not None and token is not None and port.is_live(token)


__all__ = [
    "TURN_HEADER",
    "TURN_TOKEN_ENV",
    "TurnLivePort",
    "set_turn_live",
    "turn_is_live",
]
