"""Answering one fire of Coffer's memory hook (ADR
memory-reaches-a-session-at-prompt-time-and-before-a-known-trap).

Every one of the four installed entries runs ``coffer memory hook``, which
hands the event here; what comes back is the JSON the agent reads, or nothing:

* ``SessionStart`` — the bounded index (spec memory "Deliver the index and the
  notes path at session start"), as ``additionalContext``;
* ``UserPromptSubmit`` — the top notes the prompt names (spec memory "Retrieve
  the notes a prompt names");
* ``PreToolUse`` on the shell — the first command in the session that an armed
  ``block`` trigger matches is denied, the note as the reason (spec memory
  "Guard a known trap once per session");
* ``PostToolUse`` on the shell — an armed ``context`` trigger whose error
  pattern the output shows adds the note, once per session, never blocking.

A trigger applies to a session whose note it can reach: a ``global`` note's
trigger everywhere, a repository note's trigger in that repository's sessions.
Every fire that delivers something is one audit event naming its moment and
its notes (spec memory "Audit every delivery fire").
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from coffer.application.memory.context import MemoryPort, compose_context
from coffer.application.memory.delivery import DeliveryService
from coffer.application.memory.retrieval import RetrievalService, note_file
from coffer.application.memory.session_ledger import SessionLedger
from coffer.application.memory.triggers import TriggerService
from coffer.domain.memory.delivery import (
    DELIVERY_CEILING_BYTES,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    SESSION_START,
    SHELL_TOOL_MATCHER,
    USER_PROMPT_SUBMIT,
)
from coffer.domain.memory.hook_output import (
    HELD_ONCE,
    context_output,
    deny_output,
    note_reason,
)
from coffer.domain.memory.trigger import (
    KIND_BLOCK,
    KIND_CONTEXT,
    Trigger,
    matches_command,
    matches_error,
)

logger = logging.getLogger(__name__)

#: The ``moment`` an audited fire names.
MOMENT_SESSION_START = "session_start"
MOMENT_PROMPT = "prompt"
MOMENT_GUARD = "guard"
MOMENT_ERROR = "error"


@dataclass(frozen=True)
class HookEvent:
    """What the agent handed its hook, reduced to what memory reads."""

    event: str
    session_id: str = ""
    cwd: str = ""
    prompt: str = ""
    tool_name: str = ""
    command: str = ""
    output: str = ""


class MemoryHookService:
    def __init__(
        self,
        *,
        memory: MemoryPort,
        delivery: DeliveryService,
        retrieval: RetrievalService,
        triggers: TriggerService,
        ledger: SessionLedger,
    ) -> None:
        self._memory = memory
        self._delivery = delivery
        self._retrieval = retrieval
        self._triggers = triggers
        self._ledger = ledger

    async def handle(self, agent_uid: str, ev: HookEvent) -> dict[str, Any] | None:
        """The JSON to print for one fire, or ``None`` to print nothing."""
        if ev.event == SESSION_START:
            return await self._session_start(agent_uid, ev)
        if ev.event == USER_PROMPT_SUBMIT:
            return await self._prompt(agent_uid, ev)
        if ev.tool_name != SHELL_TOOL_MATCHER:
            return None
        if ev.event == PRE_TOOL_USE:
            return await self._guard(agent_uid, ev)
        if ev.event == POST_TOOL_USE:
            return await self._error(agent_uid, ev)
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

    async def _candidates(self, ev: HookEvent, kind: str) -> list[Trigger]:
        if not ev.session_id:
            # "Once per session" needs a session to count in; without one the
            # guard stays open rather than holding every command.
            return []
        armed = [t for t in self._triggers.armed() if t.kind == kind]
        if not armed:
            return []
        await self._ledger.ready()
        _project, reachable = await self._retrieval.partitions_for(ev.cwd)
        return [
            t
            for t in armed
            if t.partition in reachable and not self._ledger.has_fired(ev.session_id, t.id)
        ]

    async def _reason(self, trigger: Trigger) -> str | None:
        for note in await self._memory.list_notes(trigger.partition):
            if note.slug == trigger.slug:
                return note_reason(note, note_file(note))
        if trigger.body:
            return f"Coffer memory, a trigger the user armed ({trigger.id}): {trigger.body}"
        return None

    async def _fire(
        self, agent_uid: str, ev: HookEvent, trigger: Trigger, moment: str
    ) -> str | None:
        reason = await self._reason(trigger)
        if reason is None:
            logger.warning("memory.trigger.note_missing; trigger=%s", trigger.id)
            return None
        self._ledger.mark_fired(ev.session_id, trigger.id)
        await self._delivery.record_fired(
            agent_uid,
            {
                "moment": moment,
                "session_id": ev.session_id,
                "event": ev.event,
                "trigger": trigger.id,
                "notes": [trigger.note],
            },
        )
        return reason

    async def _guard(self, agent_uid: str, ev: HookEvent) -> dict[str, Any] | None:
        for trigger in await self._candidates(ev, KIND_BLOCK):
            if matches_command(trigger, ev.command):
                reason = await self._fire(agent_uid, ev, trigger, MOMENT_GUARD)
                if reason is not None:
                    return deny_output(ev.event, reason + HELD_ONCE)
        return None

    async def _error(self, agent_uid: str, ev: HookEvent) -> dict[str, Any] | None:
        for trigger in await self._candidates(ev, KIND_CONTEXT):
            if matches_error(trigger, ev.command, ev.output):
                reason = await self._fire(agent_uid, ev, trigger, MOMENT_ERROR)
                if reason is not None:
                    return context_output(ev.event, reason)
        return None


__all__ = [
    "MOMENT_ERROR",
    "MOMENT_GUARD",
    "MOMENT_PROMPT",
    "MOMENT_SESSION_START",
    "HookEvent",
    "MemoryHookService",
]
