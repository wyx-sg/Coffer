"""The ``NEEDS YOU:`` sentinel: a question the agent needs the owner to answer.

Spec channels "Turn a question for the owner into buttons". The channel note
asks the agent to end with one line ``NEEDS YOU: <question> (yes / no)`` when it
needs a yes or a choice before it goes on — a guarded write's preview, a
clarification. That line is a sentinel beside ``MEDIA:``: the core strips it
from the reply and sends the question as its own message with one button per
option. A tap is sent into the conversation as the owner's own reply, so the
agent's rule "the yes comes from the user in this conversation" still holds.

Pure: parsing and the button values, no I/O.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from coffer.domain.channel.envelopes import ChoiceButton

__all__ = ["REPLY_PREFIX", "Question", "extract_question", "question_buttons", "reply_text"]

#: The callback namespace a question's buttons live in; what follows is the
#: answer, sent back as the owner's own message.
REPLY_PREFIX = "reply:"
#: Telegram caps callback data at 64 bytes, the tightest budget any transport
#: declares, so an answer is clipped to fit beside the prefix.
_CALLBACK_BYTES = 64
_MAX_OPTIONS = 4
_DEFAULT_OPTIONS = ("Yes", "No")

_SENTINEL = re.compile(r"^\s*(?:\*\*|__)?NEEDS YOU:(?:\*\*|__)?\s*(?P<rest>.+?)\s*$", re.IGNORECASE)
#: Options the question ends with, in parentheses or brackets, separated by
#: ``/`` or ``|``: ``(yes / no)``, ``[staging | live | cancel]``.
_OPTIONS = re.compile(r"[(\[](?P<options>[^()\[\]]*[/|][^()\[\]]*)[)\]]\s*$")


@dataclass(frozen=True)
class Question:
    """What the agent asked, and the options it offered (empty: more than four,
    so the owner answers in their own words)."""

    text: str
    options: tuple[str, ...]


def extract_question(reply: str) -> tuple[str, Question | None]:
    """``(reply without the sentinel, question)``; the question is ``None``
    when the reply's last non-empty line is not a ``NEEDS YOU:`` line."""
    lines = reply.rstrip().split("\n")
    if not lines:
        return reply, None
    match = _SENTINEL.match(lines[-1])
    if match is None:
        return reply, None
    rest = match.group("rest")
    options: tuple[str, ...] = _DEFAULT_OPTIONS
    found = _OPTIONS.search(rest)
    if found is not None:
        parts = [p.strip() for p in re.split(r"[/|]", found.group("options")) if p.strip()]
        options = tuple(parts) if len(parts) <= _MAX_OPTIONS else ()
        rest = rest[: found.start()].rstrip()
    body = "\n".join(lines[:-1]).rstrip()
    return body, Question(text=rest, options=options)


def _clip_bytes(text: str, budget: int) -> str:
    out = text
    while len(out.encode("utf-8")) > budget:
        out = out[:-1]
    return out


def question_buttons(question: Question) -> list[ChoiceButton]:
    """One button per option, each carrying the answer it sends."""
    room = _CALLBACK_BYTES - len(REPLY_PREFIX)
    return [
        ChoiceButton(label=option, value=REPLY_PREFIX + _clip_bytes(option, room))
        for option in question.options
    ]


def reply_text(data: str) -> str | None:
    """The answer a tapped question button sends, or ``None`` for any other tap."""
    if not data.startswith(REPLY_PREFIX):
        return None
    answer = data[len(REPLY_PREFIX) :].strip()
    return answer or None
