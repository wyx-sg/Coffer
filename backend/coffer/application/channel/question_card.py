"""A question for the owner, as a card (spec channels "Ask the owner in the chat
and take the answer back to the agent").

Pure: the text and the buttons of one question's card, the callback payload its
buttons carry, and the line the card is rewritten to once the question closes.
Nothing here sends anything; ``question_flow`` does.

A card per question. Body: the ask's context (first card only), ``❓ <question>``,
the options with their descriptions when any has one, and "Or reply with your
answer.". Buttons: one per option, one to a line, plus **Submit** on a
multi-select question, whose option buttons toggle a ``✓ `` in place.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime

from coffer.domain.channel.envelopes import ChoiceButton
from coffer.domain.chat.question import QuestionAnswer, QuestionBlock

__all__ = [
    "CALLBACK_PREFIX",
    "FOOTER",
    "SUBMIT",
    "TICK",
    "Tap",
    "callback_data",
    "card_body",
    "card_buttons",
    "closed_body",
    "closed_line",
    "local_time",
    "parse_callback",
    "question_ping",
]

#: The callback namespace a question's buttons live in.
CALLBACK_PREFIX = "ask:"
#: The option slot of the Submit button of a multi-select question.
SUBMIT = "s"
TICK = "✓ "
FOOTER = "Or reply with your answer."
_PLAIN_FOOTER = "Reply with your answer."
_STOPPED = "⏹ Stopped"


@dataclass(frozen=True)
class Tap:
    """What a tapped question button says: which question, which of its
    questions, and which option (``None``: Submit)."""

    question_id: str
    index: int
    option: int | None


def callback_data(question_id: str, index: int, option: int | None) -> str:
    """``ask:<question id>:<question index>:<option index | s>`` — about 40
    bytes, inside Telegram's 64-byte callback budget, the tightest any transport
    declares."""
    slot = SUBMIT if option is None else str(option)
    return f"{CALLBACK_PREFIX}{question_id}:{index}:{slot}"


def parse_callback(data: str) -> Tap | None:
    """The tap a payload encodes, or ``None`` for any other payload."""
    if not data.startswith(CALLBACK_PREFIX):
        return None
    parts = data[len(CALLBACK_PREFIX) :].split(":")
    if len(parts) != 3 or not parts[1].isdigit():
        return None
    if parts[2] == SUBMIT:
        return Tap(parts[0], int(parts[1]), None)
    if not parts[2].isdigit():
        return None
    return Tap(parts[0], int(parts[1]), int(parts[2]))


def _head(block: QuestionBlock, index: int) -> list[str]:
    """What opens a card: the ask's context, on the first card only."""
    return [block.context] if index == 0 and block.context else []


def card_body(block: QuestionBlock, index: int, *, buttons: bool = True) -> str:
    """The card of question ``index``. Without buttons to tap (a transport that
    has none) the options are always listed, because the reply is typed."""
    spec = block.questions[index]
    parts = _head(block, index)
    parts.append(f"❓ {spec.question}")
    if not buttons or any(o.description for o in spec.options):
        parts.append(
            "\n".join(
                f"• {o.label} — {o.description}" if o.description else f"• {o.label}"
                for o in spec.options
            )
        )
    parts.append(FOOTER if buttons else _PLAIN_FOOTER)
    return "\n\n".join(parts)


def card_buttons(
    block: QuestionBlock, index: int, ticked: frozenset[int] | set[int] = frozenset()
) -> list[ChoiceButton]:
    """One button per option, equal and one to a line; a multi-select question's
    ticked options carry a ``✓ `` and a **Submit** follows them."""
    spec = block.questions[index]
    buttons = [
        ChoiceButton(
            label=(TICK if spec.multi_select and i in ticked else "") + option.label,
            value=callback_data(block.question_id, index, i),
            own_row=True,
        )
        for i, option in enumerate(spec.options)
    ]
    if spec.multi_select:
        buttons.append(
            ChoiceButton(
                label="Submit", value=callback_data(block.question_id, index, None), own_row=True
            )
        )
    return buttons


def local_time(moment: str | None) -> str:
    """``HH:MM`` in the machine's local time; the time now when unknown."""
    when = datetime.now(tz=UTC)
    if moment:
        with contextlib.suppress(ValueError):
            when = datetime.fromisoformat(moment)
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when.astimezone().strftime("%H:%M")


def closed_line(answer: QuestionAnswer | None, *, web: bool, moment: str | None) -> str:
    """``✓ Answered: Yes · 11:42`` — ``✓ Answered in Coffer: …`` for an answer
    given on the Conversations page; ``⏹ Stopped`` when there is none."""
    if answer is None:
        return _STOPPED
    where = "Answered in Coffer" if web else "Answered"
    return f"✓ {where}: {answer.display()} · {local_time(moment)}"


def closed_body(block: QuestionBlock, index: int, line: str) -> str:
    """A rewritten card: what it asked, then how it ended — no buttons, no footer."""
    return "\n\n".join([*_head(block, index), block.questions[index].question, line])


def question_ping(elapsed: str, question: str) -> str:
    """``❓ Needs you · 4m 05s — <question>`` — the long-task ping of a turn that
    is waiting on the owner."""
    return f"❓ Needs you · {elapsed} — {question}"
