"""What the SeaTalk transport declares it can do (``ChannelCapabilities``).

Split out of ``seatalk.py`` (at its size cap).
"""

from __future__ import annotations

from coffer.domain.channel.envelopes import ChannelCapabilities
from coffer.infrastructure.channel.seatalk_send import (
    SEATALK_MENTION_EMAIL_TEMPLATE,
    SEATALK_MENTION_TEMPLATE,
)

__all__ = ["CHUNK_LIMIT", "SEATALK_CAPABILITIES", "SEATALK_RENDER_NOTES"]

CHUNK_LIMIT = 3500  # paragraph-chunking budget, in characters

#: What the agent is told renders here (spec channels "Tell a channel-driven
#: agent it is on a chat channel"), read from ``render.markdown_to_seatalk``:
#: SeaTalk's own markdown (``format: 1``) has bold, italic, inline code, fences
#: and lists; a heading is demoted to bold, a link to ``label (url)``, and a
#: table is turned into bullet rows plus an attached CSV by ``reply_shape``.
SEATALK_RENDER_NOTES = (
    "This chat renders bold, italic, inline code, code fences, and bullet or "
    "numbered lists. It does NOT render headings (they show as bold), links (write "
    "the URL itself) or tables (write one bullet per row)."
)

SEATALK_CAPABILITIES = ChannelCapabilities(
    # No live surface: while a turn runs the chat shows only the typing indicator
    # (a heartbeat keeps it up), and the finished reply is one new message. The
    # platform's stream re-types the whole message whenever anything already
    # shown changes, so a growing status message flickered (spec channels/seatalk
    # "Show only typing while a turn runs").
    # Both chat kinds: single_chat_typing and group_chat_typing. The group one
    # silently no-ops above 200 members (code 7003), so this promises an
    # attempt, never a delivered receipt.
    supports_typing=True,
    max_message_chars=CHUNK_LIMIT,
    supports_buttons=True,
    # Update Message covers interactive cards (never text).
    supports_card_update=True,
    supports_media=True,
    supports_history_fetch=True,
    # "Mention the asker in a group answer": SeaTalk mentions from a bare id, so a
    # group reply can open by @mentioning whoever asked without resolving a display
    # name. Its documented email form is the fallback for a sender with no id.
    mention_template=SEATALK_MENTION_TEMPLATE,
    mention_email_template=SEATALK_MENTION_EMAIL_TEMPLATE,
    # Any DM message can root a thread, so a DM thread is a casual reply.
    direct_threads_are_replies=True,
    render_notes=SEATALK_RENDER_NOTES,
    # A table arrives as raw pipes in a text message and fails in a card, and a
    # 200-line log is a wall on a phone: both go out as files.
    renders_tables=False,
    max_inline_code_lines=30,
    # A SeaTalk bot cannot delete a message, but it can rewrite a card it sent for 7
    # days (``/messaging/v2/update``): a group reply is therefore a card (never
    # plain text, which cannot be rewritten) and "withdrawing" it rewrites it blank.
    withdraw_window_hours=168,
)
