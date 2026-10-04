"""/api/v1/chat — answering a question the agent asked the owner (spec chat
"Pause a turn on a question for the owner").

``POST .../questions/{question_id}/answer`` is the web half of one answering
function (:func:`coffer.application.chat.questions.answer_question`) the channels
call as well: the first answer wins and a later one is ``QUESTION_CLOSED``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from coffer.application.chat import questions
from coffer.application.chat.service import ChatService
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.chat.dependencies import get_chat_service
from coffer.surfaces.http.chat.schemas import (
    AnswerQuestionIn,
    QuestionOut,
    question_out,
)
from coffer.surfaces.http.dependencies import get_actor

router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
    dependencies=[Depends(require_token)],
)


@router.post(
    "/conversations/{id}/questions/{question_id}/answer",
    response_model=QuestionOut,
)
async def answer_question(
    id: str,
    question_id: str,
    body: AnswerQuestionIn,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    actor: str = Depends(get_actor),
) -> QuestionOut:
    """Answer the question's next unanswered question(s) from the Conversations page.

    404 ``CONVERSATION_NOT_FOUND`` for an unknown conversation; 409
    ``QUESTION_CLOSED`` when the question was already answered (the first answer
    wins), cancelled, or its turn ended; 422 ``QUESTION_ANSWER_INVALID`` for an
    option the question does not offer, several options on a single-choice
    question, or an empty answer. Returns the question as it now stands.
    """
    await svc.get_conversation(id)
    block = await questions.answer_question(
        id,
        question_id,
        [questions.AnswerInput(selected=a.selected, text=a.text) for a in body.answers],
        via="web",
        by=actor,
        index=body.index,
    )
    return question_out(block)
