"""Rich messages: the agent's markdown, rendered as markdown (FR-061).

Bot API 10.1 gave Telegram a structured message format whose Markdown flavour
is very close to what an agent already writes — headings, ordered and unordered
lists, task lists, tables, fenced code, block quotations, horizontal rules,
collapsible ``<details>``, footnotes and formulas — with a 32 768-character
budget instead of 4 096.

That makes the old path (``markdown_to_telegram_html``, five tags, headings
demoted to bold, tables passed through as raw pipes, bullets replaced by a
glyph) a fallback rather than the plan. This module sends the real thing and
reports honestly when it could not, so the caller can fall back with the reply
intact.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from coffer.domain.channel.envelopes import ChoiceButton, SentMessage
from coffer.domain.channel.errors import ChannelSendFailed
from coffer.infrastructure.channel.telegram_features import Feature
from coffer.infrastructure.channel.telegram_media import inline_keyboard, routing_params

__all__ = ["RICH_MESSAGE_LIMIT", "normalize_rich_markdown", "send_rich_text"]

Call = Callable[..., Awaitable[Any]]

#: Telegram's own cap on a rich message, in UTF-8 characters. Left a little
#: short of the documented 32768 so the bold title line and any escaping this
#: module adds cannot push a body that just fitted over the edge.
RICH_MESSAGE_LIMIT = 32000

#: A fenced block or an inline code span — the regions where the source text is
#: shown verbatim and must NOT be touched by the escaping below.
_PROTECTED = re.compile(r"```.*?```|`[^`\n]+`", re.DOTALL)
#: ``$`` starts a formula in Telegram's rich Markdown. Agents emit far more
#: shell variables (``$HOME``, ``$(pwd)``) and prices than they do LaTeX, and a
#: stray one silently swallows the rest of the line into a formula.
_DOLLAR = re.compile(r"\$")


def normalize_rich_markdown(markdown: str) -> str:
    """Make agent markdown safe to hand to Telegram as rich Markdown.

    Deliberately almost a no-op: the whole point of rich messages is that the
    agent's own markdown survives. The one transformation is escaping ``$``
    outside code, because it is the single Telegram-specific meaning that
    ordinary technical prose triggers by accident.

    Everything else Telegram reads specially (``==marked==``, ``||spoiler||``,
    ``~~strike~~``) either matches its markdown meaning or appears essentially
    only inside code, which is protected here.
    """
    out: list[str] = []
    last = 0
    for match in _PROTECTED.finditer(markdown):
        out.append(_DOLLAR.sub(r"\\$", markdown[last : match.start()]))
        out.append(match.group(0))
        last = match.end()
    out.append(_DOLLAR.sub(r"\\$", markdown[last:]))
    return "".join(out)


async def send_rich_text(
    call: Call,
    chat_id: str,
    markdown: str,
    *,
    channel: str,
    feature: Feature,
    buttons: Sequence[ChoiceButton] | None = None,
    title: str = "",
    thread_id: str = "",
    reply_to_message_id: str = "",
) -> SentMessage | None:
    """Deliver ``markdown`` as one rich message.

    Returns ``None`` when the caller must fall back to the plain path — either
    the feature is already latched off, or the platform refused this send. A
    refusal is never allowed to lose the reply: only a refusal (``api_rejected``)
    yields ``None``, while a transport error is re-raised, because a send that
    merely timed out may well have landed and re-sending it would duplicate it.
    """
    if not feature.available:
        return None
    if title:
        # Rich messages have headings; use one rather than a bold line.
        markdown = f"## {title}\n\n{markdown}"
    params: dict[str, Any] = {
        "chat_id": chat_id,
        "rich_message": {"markdown": normalize_rich_markdown(markdown)},
        **routing_params(thread_id, reply_to_message_id),
    }
    if buttons:
        params["reply_markup"] = inline_keyboard(buttons)
    try:
        sent = await call("sendRichMessage", **params)
    except ChannelSendFailed as e:
        feature.note_failure(channel, e)
        if e.api_rejected:
            return None
        raise
    return SentMessage(message_id=str((sent or {}).get("message_id", "")))
