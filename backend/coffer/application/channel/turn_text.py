"""Pure text helpers for the turn renderer.

Split out of ``turn_render`` (at its size budget) the way ``turn_progress``
already was: no I/O, no platform schema — just the two shaping decisions the
renderer makes about the text it is about to hand a transport.
"""

from __future__ import annotations

import re

__all__ = ["clip_stream_preview", "mention_prefix"]

#: An id Coffer is willing to put INSIDE a platform's mention markup. Every id
#: that reaches here is opaque and platform-issued (SeaTalk's ``seatalk_id`` is
#: digits), so anything outside this set means the payload was not what we read
#: it as — and a mention built from it would reach the chat as broken markup
#: rather than as a name. Dropping it is the FR-070 silent degrade.
_MENTION_ID_SAFE = re.compile(r"\A[A-Za-z0-9_.:-]+\Z")


def mention_prefix(template: str, user_id: str) -> str:
    """The transport's @mention markup for ``user_id``, or "" when there is none.

    ``template`` is the transport's own spelling with ``{user_id}`` where the id
    goes (``ChannelCapabilities.mention_template``); substitution is a literal
    replace, so no template, no id, or an id that is not plainly an id all yield
    "" and the caller simply sends an unmentioned reply.
    """
    if not template or not user_id or not _MENTION_ID_SAFE.match(user_id):
        return ""
    return template.replace("{user_id}", user_id)


def clip_stream_preview(text: str, limit: int) -> str:
    """FR-037: clip the accumulating reply to the platform's per-message limit for
    an interim live update — a snapshot longer than the cap would be rejected.
    Keep the TAIL (the most recent words) behind a leading ellipsis, so the user
    watches the answer's latest text grow."""
    if len(text) <= limit:
        return text
    marker = "…"
    return marker + text[-(limit - len(marker)) :]
