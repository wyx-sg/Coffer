"""The Needs-you mark on a conversation of the list (spec chat "Pause a turn on a
question for the owner").

A real turn orchestrator runs a scripted adapter that asks through the same
function the Claude Code hook and ``coffer__ask`` use; the conversation routes
are driven in process over ASGI so the turn and the requests share one event
loop. The answer is taken the way a channel takes it, through
``questions.answer_question``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from coffer.application.chat import questions
from coffer.application.chat.questions import AnswerInput
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.conversation_routes import router as conversation_router
from coffer.surfaces.http.chat.dependencies import (
    get_agent_registry,
    get_chat_service,
    get_turn_orchestrator,
)
from coffer.surfaces.http.chat.turn_routes import router as turn_router
from coffer.surfaces.http.dependencies import get_resource_service
from tests.support.chat_turns import start_turn
from tests.unit.chat.conftest import make_chat_services
from tests.unit.chat.test_questions import YES_NO, _AskingProvider

pytestmark = pytest.mark.asyncio

_TOKEN = "test-token"
_BASE = "/api/v1/chat"


class _NoChannels:
    async def list(self, **_: object) -> list[Any]:
        return []


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    questions.clear_all()
    yield
    questions.clear_all()


def _app(ask_input: dict[str, Any]) -> tuple[FastAPI, Any, Any]:
    chat, orchestrator, registry = make_chat_services(provider=_AskingProvider(ask_input))
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(conversation_router)
    app.include_router(turn_router)
    app.dependency_overrides[get_chat_service] = lambda: chat
    app.dependency_overrides[get_turn_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_agent_registry] = lambda: registry
    app.dependency_overrides[get_resource_service] = lambda: _NoChannels()
    set_active_token(_TOKEN)
    return app, chat, orchestrator


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Coffer-Token": _TOKEN},
    )


async def _pending(conversation_id: str) -> Any:
    for _ in range(200):
        block = questions.pending_question_for(conversation_id)
        if block is not None:
            return block
        await asyncio.sleep(0.005)
    raise AssertionError("no question raised")


async def _drain(queue: asyncio.Queue[Any]) -> None:
    while (await asyncio.wait_for(queue.get(), 5.0)) is not None:
        pass


async def test_a_waiting_conversation_is_marked_until_it_is_answered() -> None:
    app, chat, orchestrator = _app(YES_NO)
    waiting = await chat.create_conversation(
        agent_key="builtin", channel_uid="chan-uid", peer_chat_id="p"
    )
    other = await chat.create_conversation(
        agent_key="builtin", channel_uid="chan-uid", peer_chat_id="p"
    )
    queue = await start_turn(orchestrator, waiting.id, "go")
    block = await _pending(waiting.id)

    async with _client(app) as client:
        listing = (await client.get(f"{_BASE}/conversations")).json()["conversations"]
        one = await client.get(f"{_BASE}/conversations/{waiting.id}")
        await questions.answer_question(
            waiting.id, block.question_id, [AnswerInput(selected=["Yes"])], via="chan-uid", by="o"
        )
        await _drain(queue)
        after_one = await client.get(f"{_BASE}/conversations/{waiting.id}")

    flags = {c["id"]: c["needs_you"] for c in listing}
    assert flags == {waiting.id: True, other.id: False}
    assert one.json()["needs_you"] is True
    assert after_one.json()["needs_you"] is False
