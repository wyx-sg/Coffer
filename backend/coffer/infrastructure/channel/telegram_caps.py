"""What the Telegram transport declares it can do (``ChannelCapabilities``).

Split out of ``telegram.py`` (at its size cap). Several answers follow the Bot
API features the server has not refused yet (``telegram_features``): the chunk
budget and what renders both drop back the moment rich messages are refused.
"""

from __future__ import annotations

from coffer.domain.channel.envelopes import ChannelCapabilities
from coffer.infrastructure.channel.telegram_features import FeatureSet
from coffer.infrastructure.channel.telegram_reactions import TELEGRAM_REACTIONS
from coffer.infrastructure.channel.telegram_rich import RICH_MESSAGE_LIMIT
from coffer.infrastructure.channel.telegram_text import TELEGRAM_MENTION_TEMPLATE

__all__ = ["telegram_capabilities"]

#: One ordinary message's chunk budget, when rich messages are unavailable.
_CHUNK_LIMIT = 4000

#: What the agent is told renders here (spec channels "Tell a channel-driven
#: agent it is on a chat channel") — rich messages carry GitHub-flavoured
#: Markdown almost unchanged (Bot API 10.1); the HTML fallback has five tags.
RICH_RENDER_NOTES = (
    "This chat renders headings, bold, italic, inline code, code fences, bullet, "
    "numbered and task lists, block quotes, links, and tables of up to 20 columns."
)
PLAIN_RENDER_NOTES = (
    "This chat renders bold, italic, inline code, code fences and links. Headings "
    "show as bold text and tables as raw pipes, so write one bullet per row instead."
)


def telegram_capabilities(features: FeatureSet) -> ChannelCapabilities:
    rich = features.rich_messages.available
    return ChannelCapabilities(
        supports_edit=True,
        supports_live_text=True,  # the edit IS its live surface
        supports_typing=True,
        # "Render replies in the platform's rich format": a rich message carries 32k characters
        # against an ordinary message's 4k, so the chunk budget follows whether the platform
        # still accepts them — and drops back the moment it does not.
        max_message_chars=RICH_MESSAGE_LIMIT if rich else _CHUNK_LIMIT,
        supports_buttons=True,
        supports_card_update=True,  # editMessageText rewrites text + keyboard
        supports_media=True,
        supports_groups=True,
        supports_reactions=True,
        reactions=TELEGRAM_REACTIONS,
        mention_template=TELEGRAM_MENTION_TEMPLATE,
        render_notes=RICH_RENDER_NOTES if rich else PLAIN_RENDER_NOTES,
        # ``## Details`` becomes a collapsed block in both send paths.
        collapses_details=True,
    )
