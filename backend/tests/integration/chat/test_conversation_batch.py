"""POST /api/v1/chat/conversations/batch — archive, unarchive or delete several
conversations at once, with one result per id (spec chat "Create, rename,
archive, unarchive and delete conversations")."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from coffer.application.chat.turn_orchestrator import active_turns
from coffer.domain.chat.events import AgentEvent, TextDelta
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.conversation_batch_routes import router as batch_router
from coffer.surfaces.http.chat.conversation_routes import router as conversation_router
from coffer.surfaces.http.chat.dependencies import get_chat_service, get_turn_orchestrator
from coffer.surfaces.http.dependencies import get_resource_service
from tests.support.chat_turns import start_turn
from tests.unit.chat.conftest import FakeAgentProvider, make_chat_services

_TOKEN = "test-token"
_BATCH = "/api/v1/chat/conversations/batch"
_LIST = "/api/v1/chat/conversations"


class _BlockingAdapter:
    model_id = None

    async def run_turn(self, *, history: Any, **_: object) -> AsyncIterator[AgentEvent]:
        async def gen() -> AsyncIterator[AgentEvent]:
            yield TextDelta(text="partial")
            await asyncio.sleep(3600)

        return gen()


class _NoChannels:
    async def list(self, **_: object) -> list[Any]:
        return []


def _app(chat_svc: Any, orchestrator: Any) -> FastAPI:
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(conversation_router)
    app.include_router(batch_router)
    app.dependency_overrides[get_chat_service] = lambda: chat_svc
    app.dependency_overrides[get_turn_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_resource_service] = lambda: _NoChannels()
    return app


def _create(client: TestClient, n: int) -> list[str]:
    return [client.post(_LIST, json={"agent_key": "builtin"}).json()["id"] for _ in range(n)]


def _ids(client: TestClient, archived: bool) -> set[str]:
    body = client.get(_LIST, params={"archived": archived}).json()
    return {c["id"] for c in body["conversations"]}


def test_archive_then_unarchive_with_a_missing_id_reports_each() -> None:
    chat_svc, orchestrator, _ = make_chat_services()
    set_active_token(_TOKEN)
    with TestClient(_app(chat_svc, orchestrator), headers={"X-Coffer-Token": _TOKEN}) as client:
        a, b = _create(client, 2)
        resp = client.post(_BATCH, json={"action": "archive", "ids": [a, "ghost", b]})
        assert resp.status_code == 200
        assert resp.json()["results"] == [
            {"id": a, "outcome": "done", "reason": None},
            {"id": "ghost", "outcome": "skipped", "reason": "not_found"},
            {"id": b, "outcome": "done", "reason": None},
        ]
        assert _ids(client, archived=True) == {a, b}
        assert _ids(client, archived=False) == set()

        resp = client.post(_BATCH, json={"action": "unarchive", "ids": [a]})
        assert [r["outcome"] for r in resp.json()["results"]] == ["done"]
        assert _ids(client, archived=False) == {a}
    set_active_token(None)


def test_delete_removes_the_listed_conversations() -> None:
    chat_svc, orchestrator, _ = make_chat_services()
    set_active_token(_TOKEN)
    with TestClient(_app(chat_svc, orchestrator), headers={"X-Coffer-Token": _TOKEN}) as client:
        a, b, c = _create(client, 3)
        resp = client.post(_BATCH, json={"action": "delete", "ids": [a, b]})
        assert [r["outcome"] for r in resp.json()["results"]] == ["done", "done"]
        assert _ids(client, archived=False) == {c}
    set_active_token(None)


def test_a_conversation_with_a_turn_in_flight_is_skipped_not_deleted() -> None:
    chat_svc, orchestrator, _ = make_chat_services(
        provider=FakeAgentProvider(_BlockingAdapter(), agent_key="builtin")
    )
    set_active_token(_TOKEN)

    async def _run(client: TestClient) -> None:
        running, idle = _create(client, 2)
        queue = await start_turn(orchestrator, running, "hello")
        await asyncio.wait_for(queue.get(), timeout=5.0)
        assert running in active_turns()
        resp = await asyncio.to_thread(
            client.post, _BATCH, json={"action": "delete", "ids": [running, idle]}
        )
        assert resp.json()["results"] == [
            {"id": running, "outcome": "skipped", "reason": "running"},
            {"id": idle, "outcome": "done", "reason": None},
        ]
        assert _ids(client, archived=False) == {running}
        orchestrator.cancel_turn(running)

    with TestClient(_app(chat_svc, orchestrator), headers={"X-Coffer-Token": _TOKEN}) as client:
        asyncio.run(_run(client))
    set_active_token(None)


def test_the_body_is_validated() -> None:
    chat_svc, orchestrator, _ = make_chat_services()
    set_active_token(_TOKEN)
    with TestClient(_app(chat_svc, orchestrator), headers={"X-Coffer-Token": _TOKEN}) as client:
        assert client.post(_BATCH, json={"action": "archive", "ids": []}).status_code == 422
        assert client.post(_BATCH, json={"action": "archive", "ids": ["x", "x"]}).status_code == 422
        assert client.post(_BATCH, json={"action": "burn", "ids": ["x"]}).status_code == 422
    set_active_token(None)
