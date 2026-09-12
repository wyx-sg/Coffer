"""Pure text helpers for the turn renderer.

Split out of ``turn_render`` (at its size budget) the way ``turn_progress``
already was: no I/O, no platform schema — just the two shaping decisions the
renderer makes about the text it is about to hand a transport.
"""

from __future__ import annotations

import re

__all__ = ["clip_stream_preview", "mention_prefix", "with_mention"]

#: An id Coffer is willing to put INSIDE a platform's mention markup. Every id
#: that reaches here is opaque and platform-issued (SeaTalk's ``seatalk_id`` is
#: digits), so anything outside this set means the payload was not what we read
#: it as — and a mention built from it would reach the chat as broken markup
#: rather than as a name. Dropping it is the FR-070 silent degrade.
_MENTION_ID_SAFE = re.compile(r"\A[A-Za-z0-9_.:-]+\Z")

#: The same gate for the EMAIL form of a mention, which a transport may offer as
#: a second way to address someone (SeaTalk: ``seatalk://user?email=…``). One
#: ``@``, and nothing that could break out of the attribute it sits in — quote,
#: angle bracket, ampersand, whitespace.
#:
#: An address admitted here WILL contain characters the platform's markdown
#: escaper would otherwise mangle (``first_last@example.com`` is ordinary), which
#: is why the renderer has to lift mention tags out of that pass rather than
#: relying on a tag happening to be marker-free.
_MENTION_EMAIL_SAFE = re.compile(r"\A[^\s\"'<>&@]+@[^\s\"'<>&@]+\.[^\s\"'<>&@]+\Z")


def mention_prefix(
    template: str,
    user_id: str,
    *,
    email_template: str = "",
    user_email: str = "",
) -> str:
    """The transport's @mention markup for one member, or "" when there is none.

    Each template is the transport's own spelling with ``{user_id}`` where the
    value goes (``ChannelCapabilities.mention_template`` /
    ``mention_email_template``); substitution is a literal replace, so no
    template, no value, or a value that is not plainly one yields "" and the
    caller simply sends an unmentioned reply.

    The id is PRIMARY and the email only a fallback, because that is the order of
    reliability at the platform: SeaTalk's group-@mention event always carries
    ``sender.seatalk_id``, while it warns that ``email`` (and ``employee_code``)
    come back empty for a sender outside the bot's organisation.
    """
    if template and user_id and _MENTION_ID_SAFE.match(user_id):
        return template.replace("{user_id}", user_id)
    if email_template and user_email and _MENTION_EMAIL_SAFE.match(user_email):
        return email_template.replace("{user_id}", user_email)
    return ""


def with_mention(
    body: str,
    *,
    chat_kind: str,
    id_template: str,
    user_id: str,
    email_template: str = "",
    user_email: str = "",
) -> str:
    """FR-070: ``body`` opened by an @mention of whoever asked, where that is right.

    Applied to EVERY snapshot of a reply, not just the last one, because a
    platform decides @ notifications when a message is CREATED. A streamed reply
    comes into existence at its first post (SeaTalk's ``init_stream``), so a
    mention added only to the finished snapshot RENDERS as a name — the tag is in
    the content the client shows — while notifying nobody. That was observed
    live, and it is the whole reason the mention sits this early. Mentioning from
    creation then forces the mention onto the interim snapshots too: otherwise it
    would appear, vanish for the length of the stream, and come back at the end.

    Two conditions bound it, each ruling out a mention that would be wrong:

    * a GROUP — in a 1:1 chat there is nobody to disambiguate, and a bot that @s
      you in your own DM is only shouting;
    * a transport that spells mentions from an id (or an address) alone, and a
      value to spell. Anything else degrades to an ordinary unmentioned reply.
    """
    if chat_kind != "group" or not body:
        return body
    prefix = mention_prefix(
        id_template, user_id, email_template=email_template, user_email=user_email
    )
    return f"{prefix} {body}" if prefix else body


def clip_stream_preview(text: str, limit: int) -> str:
    """FR-037: clip the accumulating reply to the platform's per-message limit for
    an interim live update — a snapshot longer than the cap would be rejected.
    Keep the TAIL (the most recent words) behind a leading ellipsis, so the user
    watches the answer's latest text grow."""
    if len(text) <= limit:
        return text
    marker = "…"
    return marker + text[-(limit - len(marker)) :]
