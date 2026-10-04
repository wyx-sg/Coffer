"""The web side of a question the agent asked the owner: the answer route, the
Needs-you mark on a conversation (spec chat "Pause a turn on a question for the
owner").

A real turn orchestrator runs a scripted adapter that asks through the same
function the Claude Code hook and ``coffer__ask`` use; the routes are driven in
process over ASGI so the turn and the requests share one event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from coffer.application.chat import questions
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.conversation_routes import router as conversation_router
from coffer.surfaces.http.chat.dependencies import (
    get_agent_registry,
    get_attachment_service,
    get_chat_service,
    get_turn_orchestrator,
)
from coffer.surfaces.http.chat.question_routes import router as question_router
from coffer.surfaces.http.chat.turn_routes import router as turn_router
from coffer.surfaces.http.dependencies import get_resource_service
from tests.support.chat_turns import start_turn
from tests.unit.chat.conftest import make_attachment_service, make_chat_services
from tests.unit.chat.test_questions import TWO, YES_NO, _AskingProvider

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
    # Mounted in the daemon's order: the literal count path before the ``{id}`` ones.
    app.include_router(question_router)
    app.include_router(conversation_router)
    app.include_router(turn_router)
    app.dependency_overrides[get_chat_service] = lambda: chat
    app.dependency_overrides[get_turn_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_agent_registry] = lambda: registry
    app.dependency_overrides[get_attachment_service] = lambda: make_attachment_service()
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


def _answer_url(conv_id: str, question_id: str) -> str:
    return f"{_BASE}/conversations/{conv_id}/questions/{question_id}/answer"


async def test_the_answer_route_answers_the_question_and_the_turn_goes_on() -> None:
    app, chat, orchestrator = _app(YES_NO)
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "deploy")
    block = await _pending(conv.id)

    async with _client(app) as client:
        waiting = await client.get(f"{_BASE}/conversations/{conv.id}/messages")
        (shown,) = [b for b in waiting.json()["messages"][-1]["content"] if b["type"] == "question"]
        resp = await client.post(
            _answer_url(conv.id, block.question_id),
            json={"answers": [{"selected": ["Yes"]}]},
            headers={"X-Coffer-Actor": "ui"},
        )
        await _drain(queue)
        history = await client.get(f"{_BASE}/conversations/{conv.id}/messages")

    assert shown["question"]["status"] == "pending", "the question is stored with the reply"
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "answered" and body["answered_via"] == "web"
    assert body["answered_by"] == "ui" and body["answers"][0]["selected"] == ["Yes"]
    reply = history.json()["messages"][-1]
    assert reply["status"] == "complete"
    (stored,) = [b for b in reply["content"] if b["type"] == "question"]
    assert stored["question"]["status"] == "answered"
    assert stored["question"]["questions"][0]["options"][1]["description"] == "Keep it local"
    assert [m["role"] for m in history.json()["messages"]] == ["user", "assistant"]


async def test_a_text_only_answer_is_accepted() -> None:
    app, chat, orchestrator = _app(YES_NO)
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "go")
    block = await _pending(conv.id)
    async with _client(app) as client:
        resp = await client.post(
            _answer_url(conv.id, block.question_id), json={"answers": [{"text": "only staging"}]}
        )
        await _drain(queue)
    assert resp.status_code == 200
    assert resp.json()["answers"][0] == {"header": "Apply", "selected": [], "text": "only staging"}


@pytest.mark.acceptance(spec="chat", scenario="the second answer to one question is refused")
async def test_a_second_answer_is_refused_and_the_first_stays() -> None:
    app, chat, orchestrator = _app(YES_NO)
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "go")
    block = await _pending(conv.id)
    # The first answer arrives from a channel, the second from the web page.
    await questions.answer_question(
        conv.id, block.question_id, [questions.AnswerInput(selected=["Yes"])], via="chan", by="o"
    )
    async with _client(app) as client:
        resp = await client.post(
            _answer_url(conv.id, block.question_id), json={"answers": [{"selected": ["No"]}]}
        )
        await _drain(queue)
        history = await client.get(f"{_BASE}/conversations/{conv.id}/messages")

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "QUESTION_CLOSED"
    (stored,) = [b for b in history.json()["messages"][-1]["content"] if b["type"] == "question"]
    assert stored["question"]["answers"][0]["selected"] == ["Yes"]
    assert stored["question"]["answered_via"] == "chan"


async def test_an_answer_that_does_not_fit_is_a_validation_error() -> None:
    app, chat, orchestrator = _app(YES_NO)
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "go")
    block = await _pending(conv.id)
    async with _client(app) as client:
        bad_label = await client.post(
            _answer_url(conv.id, block.question_id), json={"answers": [{"selected": ["Maybe"]}]}
        )
        empty = await client.post(
            _answer_url(conv.id, block.question_id), json={"answers": [{"selected": []}]}
        )
        no_body = await client.post(_answer_url(conv.id, block.question_id), json={"answers": []})
        missing = await client.post(
            _answer_url("nope", block.question_id), json={"answers": [{"text": "x"}]}
        )
    assert bad_label.status_code == 422
    assert bad_label.json()["error"]["code"] == "QUESTION_ANSWER_INVALID"
    assert empty.status_code == 422 and no_body.status_code == 422
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "CONVERSATION_NOT_FOUND"
    assert questions.pending_question_for(conv.id) is not None, "nothing was answered"
    orchestrator.interrupt_turn(conv.id)
    await _drain(queue)


async def test_a_question_index_guards_against_answering_the_next_card() -> None:
    app, chat, orchestrator = _app(TWO)
    conv = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, conv.id, "go")
    block = await _pending(conv.id)
    async with _client(app) as client:
        first = await client.post(
            _answer_url(conv.id, block.question_id),
            json={"answers": [{"selected": ["staging"]}], "index": 0},
        )
        again = await client.post(
            _answer_url(conv.id, block.question_id),
            json={"answers": [{"selected": ["live"]}], "index": 0},
        )
        last = await client.post(
            _answer_url(conv.id, block.question_id),
            json={"answers": [{"selected": ["api"]}], "index": 1},
        )
        await _drain(queue)
    assert first.json()["status"] == "pending" and len(first.json()["answers"]) == 1
    assert again.status_code == 409
    assert last.json()["status"] == "answered"
    assert [a["selected"] for a in last.json()["answers"]] == [["staging"], ["api"]]


async def test_a_waiting_conversation_is_marked_until_it_is_answered() -> None:
    app, chat, orchestrator = _app(YES_NO)
    waiting = await chat.create_conversation(agent_key="builtin")
    other = await chat.create_conversation(agent_key="builtin")
    queue = await start_turn(orchestrator, waiting.id, "go")
    block = await _pending(waiting.id)

    async with _client(app) as client:
        listing = (await client.get(f"{_BASE}/conversations")).json()["conversations"]
        one = await client.get(f"{_BASE}/conversations/{waiting.id}")
        await client.post(
            _answer_url(waiting.id, block.question_id), json={"answers": [{"selected": ["Yes"]}]}
        )
        await _drain(queue)
        after_one = await client.get(f"{_BASE}/conversations/{waiting.id}")

    flags = {c["id"]: c["needs_you"] for c in listing}
    assert flags == {waiting.id: True, other.id: False}
    assert one.json()["needs_you"] is True
    assert after_one.json()["needs_you"] is False
