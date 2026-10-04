"""POST /api/v1/chat/conversations/batch — archive, unarchive or delete several
conversations in one call (spec chat "Create, rename, archive, unarchive and
delete conversations").

Each id is handled on its own, so one that is gone or busy never blocks the
rest: the answer lists what became of every id. A conversation with a turn in
flight is never deleted here (it is skipped as ``running``); the single delete
route is where a person confirms stopping a running turn.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator

from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.application.chat.turn_state import is_running
from coffer.domain.chat.errors import ConversationNotFound
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.chat.dependencies import get_chat_service, get_turn_orchestrator

_log = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
    dependencies=[Depends(require_token)],
)


class ConversationBatchIn(BaseModel):
    """What to do, and to which conversations (at most 200, each listed once)."""

    action: Literal["archive", "unarchive", "delete"]
    ids: list[str] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _distinct(self) -> ConversationBatchIn:
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("a conversation is listed twice")
        return self


class ConversationBatchResultOut(BaseModel):
    id: str
    outcome: Literal["done", "skipped"]
    #: Why a skipped one was left as it is.
    reason: Literal["not_found", "running", "failed"] | None = None


class ConversationBatchOut(BaseModel):
    results: list[ConversationBatchResultOut]


def _skipped(
    id: str, reason: Literal["not_found", "running", "failed"]
) -> ConversationBatchResultOut:
    return ConversationBatchResultOut(id=id, outcome="skipped", reason=reason)


@router.post("/conversations/batch", response_model=ConversationBatchOut)
async def batch_conversations(
    body: ConversationBatchIn,
    svc: ChatService = Depends(get_chat_service),  # noqa: B008
    orchestrator: TurnOrchestrator = Depends(get_turn_orchestrator),  # noqa: B008
) -> ConversationBatchOut:
    """Apply ``action`` to every listed conversation; one result per id, in order."""
    results: list[ConversationBatchResultOut] = []
    for id in body.ids:
        if body.action == "delete" and is_running(id):
            results.append(_skipped(id, "running"))
            continue
        try:
            if body.action == "archive":
                await svc.archive_conversation(id)
            elif body.action == "unarchive":
                await svc.unarchive_conversation(id)
            else:
                await svc.delete_conversation(id, cancel_turn_fn=orchestrator.cancel_turn)
        except ConversationNotFound:
            results.append(_skipped(id, "not_found"))
        except Exception:
            _log.exception("batch %s of conversation %s failed", body.action, id)
            results.append(_skipped(id, "failed"))
        else:
            results.append(ConversationBatchResultOut(id=id, outcome="done"))
    return ConversationBatchOut(results=results)
