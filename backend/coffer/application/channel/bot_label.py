"""How the bot is called in its own chat text: by its name, never by an id."""

from __future__ import annotations

from coffer.application.channel.ports import ChannelBinding

__all__ = ["bot_handle", "bot_name"]


def bot_name(binding: ChannelBinding) -> str:
    """The channel's display name (``Team bot``)."""
    return binding.resource.name


def bot_handle(binding: ChannelBinding) -> str:
    """``@username`` where the platform has one (Telegram), else the name."""
    identity = getattr(binding.adapter, "identity", None)
    username = getattr(identity, "username", None)
    return f"@{username}" if username else bot_name(binding)
