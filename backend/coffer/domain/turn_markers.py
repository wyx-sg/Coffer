"""The role markers a channel turn's text is built from, and the guard that keeps
untrusted text from forging one.

A channel turn hands the agent several kinds of text in one string: where the
message came from, the thread around it, the message it quotes, a chat record
someone forwarded, the person's own words, and the files that came with them — or, for a turn a
scheduled task started, the task and what Coffer gathered for it.
Each kind sits in its own block that opens with a heading line and closes with an
end line (spec channels "Open every turn with its message origin" and the
requirements after it), so the agent can always tell who wrote what.

Every marker is an English constant here, once, so the turn builders, the agent
adapters, the docs and the tests all name the same strings.

**The forgery guard** (:func:`neutralise`). Everything inside a block except
Coffer's own lines is untrusted: forwarded items, the quote, thread messages,
sender names, document text, and the person's own words too. A line of such text
that begins — after any indentation — with ``[`` followed by one of the marker
names below (any letter case) would read as a block boundary. The guard puts a
backslash in front of that ``[``: ``[End of user message]`` becomes
``\\[End of user message]``. The line keeps its words and no longer begins with a
marker, so only Coffer's own lines open or close a block.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

__all__ = [
    "ATTACHMENTS",
    "ATTACHMENTS_END",
    "DOCUMENT",
    "DOCUMENT_END",
    "FORWARDED",
    "FORWARDED_END",
    "MATERIAL",
    "MATERIAL_END",
    "ORIGIN",
    "ORIGIN_END",
    "QUOTED",
    "QUOTED_END",
    "SCHEDULED",
    "SCHEDULED_END",
    "THREAD",
    "THREAD_END",
    "THREAD_NEW",
    "USER",
    "USER_END",
    "VOICE_TRANSCRIPT",
    "VOICE_TRANSCRIPT_END",
    "block",
    "heading",
    "neutralise",
    "when",
]

#: Where the turn came from: platform, channel, chat, thread, sender, time.
ORIGIN = "Message origin"
ORIGIN_END = "End of message origin"
#: A chat record the person forwarded. Provenance only — never an instruction
#: about how to treat it; what to do with it is the person's own message's call.
FORWARDED = "Forwarded chat record — forwarded by the user; written by others"
FORWARDED_END = "End of forwarded chat record"
#: The message the person replied to.
QUOTED = "Quoted message — the message the user is replying to"
QUOTED_END = "End of quoted message"
#: The thread's slice on a conversation's first turn there, and what was posted
#: since on every later one.
THREAD = "Thread messages"
THREAD_NEW = "New thread messages since your last turn in this thread"
THREAD_END = "End of thread messages"
#: The person's own words; ``User message i/N`` when one turn holds N messages.
USER = "User message"
USER_END = "End of user message"
#: The files the turn carries, each as ``#n from <source>: …``.
ATTACHMENTS = "Attachments"
ATTACHMENTS_END = "End of attachments"
#: A voice attachment an agent's speech-to-text turned into words.
VOICE_TRANSCRIPT = "Voice message transcript"
VOICE_TRANSCRIPT_END = "End of voice message transcript"
#: A document attachment extracted to text.
DOCUMENT = "Document"
DOCUMENT_END = "End of document"
#: A turn a scheduled task started: which task, when it was due, what to do.
SCHEDULED = "Scheduled task"
SCHEDULED_END = "End of scheduled task"
#: What Coffer gathered for a scheduled run (the day's channel conversations).
MATERIAL = "Material"
MATERIAL_END = "End of material"

#: The names a forged line could start with. A heading is matched on its leading
#: words, so ``[Forwarded chat record]`` and ``[User message 2/3]`` both count.
_NAMES = (
    ORIGIN,
    "Forwarded chat record",
    "Quoted message",
    THREAD,
    "New thread messages",
    USER,
    ATTACHMENTS,
    VOICE_TRANSCRIPT,
    DOCUMENT,
    SCHEDULED,
    MATERIAL,
)
_FORGED = re.compile(
    r"^(\s*)\[(?=(?:End of )?(?:" + "|".join(re.escape(n) for n in _NAMES) + r")(?:[\]\s:—#/]|$))",
    re.IGNORECASE | re.MULTILINE,
)


def neutralise(text: str) -> str:
    """``text`` with every line that would open or close a block defused by a
    backslash before its ``[`` (see the module docstring)."""
    return _FORGED.sub(r"\1\\[", text)


def heading(name: str) -> str:
    """A block's heading or end line: ``[<name>]``."""
    return f"[{name}]"


def block(name: str, end: str, lines: list[str]) -> str:
    """``lines`` between a heading and an end line. The caller has already
    neutralised whatever untrusted text the lines hold."""
    return "\n".join([heading(name), *lines, heading(end)])


def when(moment: datetime | None) -> str:
    """A platform timestamp as ``YYYY-MM-DD HH:MM UTC``; ``""`` when the platform
    gave none (an unset epoch counts as none — it is not a time anyone sent at)."""
    if moment is None or moment.timestamp() <= 0:
        return ""
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")
