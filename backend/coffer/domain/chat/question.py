"""A question an agent asks the owner mid-turn (spec chat "Pause a turn on a
question for the owner").

The question is a block held in memory while its turn waits: the same shape for
``coffer__ask`` and for Claude Code's ``AskUserQuestion``. This module
holds the pure model — the block, its states, the validation of an ask's input
and of the owner's answers — and nothing about how a question is waited on.

Several questions in one ask are answered one at a time, in order: ``answers``
holds the answers given so far (a prefix of ``questions``) and the block turns
``answered`` once the last one is in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from coffer.domain.chat.errors import QuestionAnswerInvalid

QuestionStatus = Literal["pending", "answered", "cancelled"]

MAX_QUESTIONS = 4
MIN_OPTIONS = 2
MAX_OPTIONS = 4
_MAX_TEXT = 4000


@dataclass(frozen=True)
class QuestionOption:
    label: str
    description: str | None = None


@dataclass(frozen=True)
class QuestionSpec:
    """One question of an ask."""

    header: str
    question: str
    options: tuple[QuestionOption, ...]
    multi_select: bool = False


@dataclass(frozen=True)
class QuestionAnswer:
    """The answer to one question: the chosen labels and/or free text."""

    header: str
    selected: tuple[str, ...] = ()
    text: str | None = None

    def display(self) -> str:
        """The answer as one string — what the agent receives for the question."""
        parts = [*self.selected]
        if self.text:
            parts.append(self.text)
        return ", ".join(parts)


@dataclass(frozen=True)
class QuestionBlock:
    """The ``question`` content block."""

    question_id: str
    questions: tuple[QuestionSpec, ...]
    context: str | None = None
    status: QuestionStatus = "pending"
    answers: tuple[QuestionAnswer, ...] = field(default_factory=tuple)
    answered_via: str | None = None
    answered_by: str | None = None
    answered_at: str | None = None
    type: Literal["question"] = "question"

    @property
    def next_index(self) -> int:
        """The index of the first unanswered question."""
        return len(self.answers)


def parse_ask_input(arguments: dict[str, Any]) -> tuple[str | None, tuple[QuestionSpec, ...]]:
    """The ``(context, questions)`` of a ``coffer__ask`` / ``AskUserQuestion`` input.

    Accepts ``multi_select`` and Claude Code's ``multiSelect``. Raises ``ValueError``
    naming what is wrong, so the calling agent can correct the call.
    """
    raw = arguments.get("questions")
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_QUESTIONS:
        raise ValueError(f"questions must hold 1 to {MAX_QUESTIONS} questions")
    context = arguments.get("context")
    if context is not None and not isinstance(context, str):
        raise ValueError("context must be a string")
    specs: list[QuestionSpec] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each question must be an object")
        question = item.get("question")
        if not isinstance(question, str) or not question.strip():
            raise ValueError("each question needs the text of the question")
        header = item.get("header")
        options_raw = item.get("options")
        if not isinstance(options_raw, list) or not MIN_OPTIONS <= len(options_raw) <= MAX_OPTIONS:
            raise ValueError(f"each question needs {MIN_OPTIONS} to {MAX_OPTIONS} options")
        options: list[QuestionOption] = []
        for opt in options_raw:
            if not isinstance(opt, dict) or not isinstance(opt.get("label"), str):
                raise ValueError("each option needs a label")
            label = opt["label"].strip()
            if not label:
                raise ValueError("each option needs a label")
            description = opt.get("description")
            options.append(
                QuestionOption(
                    label=label,
                    description=description
                    if isinstance(description, str) and description
                    else None,
                )
            )
        if len({o.label for o in options}) != len(options):
            raise ValueError("the options of a question must have different labels")
        multi = item.get("multi_select", item.get("multiSelect", False))
        specs.append(
            QuestionSpec(
                header=header.strip() if isinstance(header, str) else "",
                question=question.strip(),
                options=tuple(options),
                multi_select=bool(multi),
            )
        )
    return (context.strip() or None) if isinstance(context, str) else None, tuple(specs)


def check_answer(spec: QuestionSpec, selected: list[str], text: str | None) -> QuestionAnswer:
    """The answer to ``spec`` made of ``selected`` labels and/or ``text``.

    Raises ``QuestionAnswerInvalid`` for a label that is not an option, several
    labels on a single-choice question, or no answer at all. Free text is always
    an answer (the "Other" the owner types).
    """
    text = (text or "").strip() or None
    if text is not None and len(text) > _MAX_TEXT:
        raise QuestionAnswerInvalid(f"the text answer is over {_MAX_TEXT} characters")
    labels = {o.label for o in spec.options}
    unknown = [s for s in selected if s not in labels]
    if unknown:
        raise QuestionAnswerInvalid(f"not an option of this question: {unknown[0]!r}")
    if len(set(selected)) != len(selected):
        raise QuestionAnswerInvalid("an option was chosen twice")
    if len(selected) > 1 and not spec.multi_select:
        raise QuestionAnswerInvalid("this question takes one option")
    if not selected and text is None:
        raise QuestionAnswerInvalid("an answer needs an option or some text")
    return QuestionAnswer(header=spec.header, selected=tuple(selected), text=text)
