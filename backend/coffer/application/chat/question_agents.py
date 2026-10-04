"""How the agents reach a Coffer question: ``coffer__ask`` (the gateway's port)
and Claude Code's ``AskUserQuestion`` (the adapter's ``ask_owner``). Both end in
:func:`coffer.application.chat.questions.raise_question`."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from coffer.application.chat import questions
from coffer.application.chat.questions import QuestionOutcome
from coffer.domain.chat.question import QuestionBlock


def answers_payload(block: QuestionBlock) -> list[dict[str, Any]]:
    """The answers as ``coffer__ask`` returns them."""
    return [
        {
            "header": a.header,
            "question": q.question,
            "selected": list(a.selected),
            "text": a.text,
        }
        for q, a in zip(block.questions, block.answers, strict=False)
    ]


class QuestionService:
    """The chat kind's side of :class:`coffer.application.turn_ask.TurnAskPort`."""

    def is_live(self, token: str | None) -> bool:
        return questions.turn_is_live(token)

    async def ask(self, token: str, arguments: dict[str, Any]) -> dict[str, Any]:
        outcome = await questions.raise_question(token, arguments)
        if outcome.answered:
            return {"answered": True, "answers": answers_payload(outcome.block)}
        return {"answered": False, "message": outcome.message}


#: How an adapter asks the owner: the turn's token is already bound in.
AskOwner = Callable[[dict[str, Any]], Awaitable[QuestionOutcome]]


def asker_for(conversation_id: str) -> AskOwner | None:
    """The ``ask_owner`` function for the conversation's live turn, or ``None``
    when no turn is registered (the adapter then lets the agent's own dialog stand)."""
    token = questions.token_for(conversation_id)
    if token is None:
        return None

    async def _ask(arguments: dict[str, Any]) -> QuestionOutcome:
        return await questions.raise_question(token, arguments)

    return _ask


__all__ = ["AskOwner", "QuestionService", "answers_payload", "asker_for"]
