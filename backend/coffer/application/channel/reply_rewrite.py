"""A reply too long for a chat is not sent: the agent is asked for the short
version, which ends by offering the full one (spec channels "Ask for the short
version of a reply too long for a chat"; ADRs long-channel-reply-is-rewritten-short,
a-channel-reply-is-plain-text).

The reply style already asks for the answer in a few lines and a full report
only as a file on request. A model that ignores it would otherwise land a wall
of text on a phone. Cutting it would leave half a message; storing it would keep
reply text Coffer never keeps. So the same conversation is asked, once, to say
it again short and to offer the full report — which the agent still holds in its
own session and sends as a file when the owner asks for it in a message.

Pure: no I/O. The renderer measures and the driver runs the follow-up turn.
"""

from __future__ import annotations

import re

__all__ = [
    "MAX_REPLY_CHARS",
    "MAX_REPLY_LINES",
    "measure",
    "media_lines",
    "rewrite_prompt",
    "too_long",
]

#: Past either bound a reply is too long to read as a chat message: about two
#: phone screens. Lines count only those with text; characters count every one,
#: so a dense paragraph of CJK text trips the bound as surely as many lines do.
MAX_REPLY_LINES = 20
MAX_REPLY_CHARS = 1500

_MEDIA_LINE = re.compile(r"^\s*MEDIA:.*$", re.MULTILINE)
_DETAILS = re.compile(r"^#{1,3}[ \t]+details[ \t]*:?[ \t]*$", re.IGNORECASE | re.MULTILINE)


def measure(text: str, *, collapses_details: bool = False) -> tuple[int, int]:
    """``(lines with text, characters)`` of what a reader would scroll through:
    file sentinels are uploads, not text, and a details section a transport
    collapses is out of sight."""
    body = _MEDIA_LINE.sub("", text)
    if collapses_details:
        match = _DETAILS.search(body)
        if match is not None:
            body = body[: match.start()]
    body = body.strip()
    lines = sum(1 for line in body.splitlines() if line.strip())
    return lines, len(body)


def media_lines(text: str) -> str:
    """The reply's ``MEDIA:`` lines, one per line: the files it sends, which the
    short version carries over rather than losing them with the long text."""
    return "\n".join(m.group(0).strip() for m in _MEDIA_LINE.finditer(text))


def too_long(text: str, *, collapses_details: bool = False) -> bool:
    lines, chars = measure(text, collapses_details=collapses_details)
    return lines > MAX_REPLY_LINES or chars > MAX_REPLY_CHARS


def rewrite_prompt(lines: int) -> str:
    """The follow-up turn's text. It names Coffer as its author, so the agent —
    and anyone reading the session later — can tell it from the owner."""
    return (
        f"[Coffer] Your last reply ({lines} lines) was too long for a chat, so it "
        "was not sent. Write it again for the chat: only the conclusion and what "
        "the reader needs to act on, in at most 5 lines, in the same language, "
        "ending with one short line that offers the full report as a file if the "
        "reader wants it. Files you "
        "attached with MEDIA: lines are sent with it, so do not repeat them. Do "
        "not call tools and do not mention this note."
    )
