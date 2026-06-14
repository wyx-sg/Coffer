"""Integration test: deleting a conversation cancels and DISCARDS its turn (FR-022).

- The DELETE route forwards ``orchestrator.cancel_turn`` to ``ChatService``.
- ``delete_conversation``, given ``cancel_turn_fn``, cancels the in-flight turn
  on the *discard* path — no partial assistant message, no terminal ``TurnDone``
  (this is what distinguishes deletion from user interruption).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coffer.application.chat.ports import ApprovalGate
from coffer.application.chat.turn_orchestrator import (
    TurnOrchestrator,
    active_turns,
    clear_active_turns,
)
from coffer.domain.chat.events import AgentEvent, TextDelta
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.chat.conversation_routes import router as conversation_router
from coffer.surfaces.http.chat.model_routes import router as model_router
from coffer.surfaces.http.chat.turn_routes import router as turn_router
from coffer.surfaces.http.dependencies import (
    get_agent_registry,
    get_chat_service,
    get_model_service,
    get_turn_orchestrator,
)
from tests.unit.chat.conftest import FakeAgentProvider, make_chat_services

_TOKEN = "test-token"


class _BlockingAdapter:
    """Emits one event, then blocks until the turn task is cancelled."""

    model_id = None

    async def run_turn(self, *, history: Any, approvals: ApprovalGate) -> AsyncIterator[AgentEvent]:
        async def gen() -> AsyncIterator[AgentEvent]:
            yield TextDelta(text="partial")
            await asyncio.sleep(3600)

        return gen()


def _build_app(chat_svc: Any, model_svc: Any, orchestrator: Any, registry: Any) -> FastAPI:
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(conversation_router)
    app.include_router(turn_router)
    app.include_router(model_router)
    app.dependency_overrides[get_chat_service] = lambda: chat_svc
    app.dependency_overrides[get_model_service] = lambda: model_svc
    app.dependency_overrides[get_turn_orchestrator] = lambda: orchestrator
    app.dependency_overrides[get_agent_registry] = lambda: registry
    return app


@pytest.fixture(autouse=True)
def _reset_turns():  # type: ignore[no-untyped-def]
    clear_active_turns()
    yield
    clear_active_turns()


def test_delete_conversation_route_passes_cancel_fn_to_service() -> None:
    """DELETE /conversations/{id} passes orchestrator.cancel_turn to the service."""
    chat_svc, model_svc, orchestrator, registry = make_chat_services()
    app = _build_app(chat_svc, model_svc, orchestrator, registry)
    set_active_token(_TOKEN)

    captured: list[Callable[..., Any] | None] = []
    original = chat_svc.delete_conversation

    async def _capturing_delete(
        conversation_id: str,
        *,
        actor: str = "user",
        cancel_turn_fn: Callable[..., Any] | None = None,
    ) -> None:
        captured.append(cancel_turn_fn)
        await original(conversation_id, actor=actor, cancel_turn_fn=cancel_turn_fn)

    chat_svc.delete_conversation = _capturing_delete  # type: ignore[method-assign]

    with TestClient(app, headers={"X-Coffer-Token": _TOKEN}) as client:
        conv_id = client.post("/api/v1/chat/conversations", json={"agent_key": "builtin"}).json()["id"]
        resp = client.delete(f"/api/v1/chat/conversations/{conv_id}")
        assert resp.status_code == 204

    assert len(captured) == 1
    fn = captured[0]
    assert fn is not None
    assert fn.__func__ is TurnOrchestrator.cancel_turn  # type: ignore[union-attr]
    assert fn.__self__ is orchestrator  # type: ignore[union-attr]
    set_active_token(None)


@pytest.mark.asyncio
async def test_delete_discards_an_in_flight_turn() -> None:
    """delete_conversation cancels a live turn on the discard path.

    Unlike interruption, the discard path emits no terminal TurnDone and
    persists no partial assistant message; the task simply leaves the registry.
    """
    chat_svc, _model_svc, orchestrator, _registry = make_chat_services(
        provider=FakeAgentProvider(_BlockingAdapter(), agent_key="builtin")
    )
    conv = await chat_svc.create_conversation(agent_key="builtin")

    queue = await orchestrator.start_turn(conv.id, "hello")
    first = await asyncio.wait_for(queue.get(), timeout=5.0)
    assert isinstance(first, TextDelta)
    assert conv.id in active_turns()

    await chat_svc.delete_conversation(conv.id, cancel_turn_fn=orchestrator.cancel_turn)

    # Drain the queue: the discard path emits only the end-of-stream sentinel.
    drained: list[AgentEvent] = []
    while True:
        item = await asyncio.wait_for(queue.get(), timeout=5.0)
        if item is None:
            break
        drained.append(item)

    assert drained == []  # no terminal TurnDone — the turn was discarded
    assert conv.id not in active_turns()
