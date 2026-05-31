"""Test doubles for the chat application layer.

A runtime is non-local + non-deterministic (it drives an LLM or a subprocess),
so a fake at the ``AgentRuntime`` boundary is the right tool — the real
runtimes get their own narrower tests. The fake replays a scripted event list
and implements the confirmation/stop protocol faithfully.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from coffer.domain.chat.runtime import (
    ChatTurnRequest,
    ConfirmationRequest,
    DoneEvent,
    RuntimeEvent,
    ToolResultEvent,
)
from coffer.domain.errors import LlmNotConfigured
from coffer.domain.resource import ResourceRef


class FakeRuntime:
    """Replays ``events`` in order, ending with an automatic ``DoneEvent``.

    When it replays a ``ConfirmationRequest`` it suspends until
    ``resolve_confirmation`` is called, then emits a ``ToolResultEvent`` whose
    ``ok`` reflects the decision (``stop`` makes the suspended turn end early).
    """

    def __init__(self, events: list[RuntimeEvent]) -> None:
        self._events = events
        self._decisions: dict[str, asyncio.Future[bool]] = {}
        self._stopped = asyncio.Event()
        self.last_request: ChatTurnRequest | None = None

    async def stream(self, request: ChatTurnRequest) -> AsyncIterator[RuntimeEvent]:
        self.last_request = request
        for ev in self._events:
            if self._stopped.is_set():
                return
            if isinstance(ev, ConfirmationRequest):
                # Register the decision future BEFORE yielding, so a decision
                # (or stop) that arrives while the consumer holds the event can
                # be matched — it need not wait for us to re-enter and await.
                fut: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
                self._decisions[ev.id] = fut
                yield ev
                if self._stopped.is_set():
                    return
                approve = await fut
                if self._stopped.is_set():
                    return
                yield ToolResultEvent(
                    id=ev.id,
                    tool=ev.tool,
                    ok=approve,
                    summary="ran" if approve else "declined by user",
                )
            else:
                yield ev
        if self._stopped.is_set():
            return
        yield DoneEvent()

    async def resolve_confirmation(self, request_id: str, approve: bool) -> None:
        fut = self._decisions.get(request_id)
        if fut is not None and not fut.done():
            fut.set_result(approve)

    async def stop(self) -> None:
        self._stopped.set()
        for fut in self._decisions.values():
            if not fut.done():
                fut.set_result(False)


class FakeRuntimeFactory:
    """Hands out a programmed ``FakeRuntime`` (or raises to exercise 503)."""

    def __init__(self) -> None:
        self.runtime: FakeRuntime | None = None
        self.raise_llm_not_configured = False
        self.built: list[tuple[ResourceRef, dict[str, Any]]] = []

    def build(self, *, target: ResourceRef, config: dict[str, Any]):
        self.built.append((target, config))
        if self.raise_llm_not_configured:
            raise LlmNotConfigured("no provider key configured")
        return self.runtime if self.runtime is not None else FakeRuntime([])


class FakeTitleGenerator:
    def __init__(self, title: str | None = "Generated Title") -> None:
        self._title = title
        self.calls: list[tuple[str, str]] = []

    async def generate(self, user_message: str, assistant_message: str) -> str | None:
        self.calls.append((user_message, assistant_message))
        return self._title
