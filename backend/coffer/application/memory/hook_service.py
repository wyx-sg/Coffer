"""Answering one fire of Coffer's memory hook.

Both installed entries run ``coffer memory hook``, which hands the event here;
what comes back is the JSON the agent reads, or nothing:

* ``SessionStart`` — the bounded index (spec memory "Deliver the index and the
  notes path at session start"), as ``additionalContext``;
* ``UserPromptSubmit`` — the top notes the prompt names (spec memory "Retrieve
  the notes a prompt names");

Every fire that delivers something is one audit event naming its moment and
its notes (spec memory "Audit every delivery fire").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from coffer.application.memory.context import MemoryPort, compose_context
from coffer.application.memory.delivery import DeliveryService
from coffer.application.memory.retrieval import RetrievalService
from coffer.domain.memory.delivery import (
    DELIVERY_CEILING_BYTES,
    SESSION_START,
    USER_PROMPT_SUBMIT,
)
from coffer.domain.memory.hook_output import context_output

#: The ``moment`` an audited fire names.
MOMENT_SESSION_START = "session_start"
MOMENT_PROMPT = "prompt"


@dataclass(frozen=True)
class HookEvent:
    """What the agent handed its hook, reduced to what memory reads."""

    event: str
    session_id: str = ""
    cwd: str = ""
    prompt: str = ""


class MemoryHookService:
    def __init__(
        self,
        *,
        memory: MemoryPort,
        delivery: DeliveryService,
        retrieval: RetrievalService,
    ) -> None:
        self._memory = memory
        self._delivery = delivery
        self._retrieval = retrieval

    async def handle(self, agent_uid: str, ev: HookEvent) -> dict[str, Any] | None:
        """The JSON to print for one fire, or ``None`` to print nothing."""
        if ev.event == SESSION_START:
            return await self._session_start(agent_uid, ev)
        if ev.event == USER_PROMPT_SUBMIT:
            return await self._prompt(agent_uid, ev)
        return None

    async def _session_start(self, agent_uid: str, ev: HookEvent) -> dict[str, Any] | None:
        composed = await compose_context(
            self._memory, cwd=ev.cwd, ceiling_bytes=DELIVERY_CEILING_BYTES
        )
        await self._delivery.record_fired(
            agent_uid,
            {"moment": MOMENT_SESSION_START, "session_id": ev.session_id, "event": ev.event},
        )
        if not composed.text:
            return None
        return context_output(ev.event, composed.text)

    async def _prompt(self, agent_uid: str, ev: HookEvent) -> dict[str, Any] | None:
        got = await self._retrieval.retrieve(cwd=ev.cwd, prompt=ev.prompt, session_id=ev.session_id)
        if not got.text:
            return None
        await self._delivery.record_fired(
            agent_uid,
            {
                "moment": MOMENT_PROMPT,
                "session_id": ev.session_id,
                "event": ev.event,
                "notes": list(got.notes),
            },
        )
        return context_output(ev.event, got.text)


__all__ = [
    "MOMENT_PROMPT",
    "MOMENT_SESSION_START",
    "HookEvent",
    "MemoryHookService",
]
