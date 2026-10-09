"""Build the binding a started channel's adapter is registered under."""

from __future__ import annotations

from coffer.application.channel.inbound import ChannelBinding
from coffer.application.channel.ports import ChannelAdapter
from coffer.application.channel.wanted import Routing
from coffer.domain.channel.config import SeaTalkChannelConfig, TelegramChannelConfig
from coffer.domain.resource import Resource


def make_binding(
    resource: Resource,
    parsed: TelegramChannelConfig | SeaTalkChannelConfig,
    routing: Routing,
    adapter: ChannelAdapter,
) -> ChannelBinding:
    """The parsed config's ``default_agent`` is an agent UID; what the turn
    platform routes on is the key the gate resolved it to (``wanted.Routing``).
    Reading the uid straight off the parsed config here is exactly the mistake
    the single crossing exists to make impossible."""
    return ChannelBinding(
        resource=resource,
        channel_type=parsed.channel_type,
        default_agent=routing.default_agent,
        default_agent_config=parsed.default_agent_config,
        adapter=adapter,
        require_mention=parsed.require_mention,
        ignore_other_mentions=parsed.ignore_other_mentions,
        wait_after_text_seconds=parsed.wait_after_text_seconds,
        wait_after_forward_seconds=parsed.wait_after_forward_seconds,
        show_steps=parsed.show_steps,
        new_conversation_after_idle_hours=parsed.new_conversation_after_idle_hours,
        agent_scope=routing.agent_scope,
        directories=tuple(parsed.directories),
    )
