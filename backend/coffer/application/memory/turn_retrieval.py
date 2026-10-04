"""Memory for a turn Coffer drives itself (spec memory "Deliver to channel turns
through the system prompt", "Retrieve the notes a prompt names for a channel
turn").

Coffer spawns a channel-driven turn's agent and owns its context, so the two
moments a hook would answer at the start of a turn are answered here instead,
and the memory hook firing inside that process leaves both to the turn
(``coffer.domain.channel_turn``) — one owner for each, so nothing arrives, or
is counted, twice:

* the **index**, by the same ``compose_context`` the ``SessionStart`` hook
  answers through, for the turn's system prompt;
* the **notes the prompt names**, by the same ``RetrievalService`` the
  ``UserPromptSubmit`` hook answers through — the same ranking, floor, top
  three, 1.5 KB ceiling and per-session ledger — keyed on the conversation.

Each is audited as a fire of the answering agent, ``session_start`` and
``prompt``, just as a hook fire is (spec memory "Audit every delivery fire").
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol

from coffer.application.memory.context import MemoryPort, compose_context
from coffer.application.memory.hook_service import MOMENT_PROMPT, MOMENT_SESSION_START
from coffer.application.memory.retrieval import RetrievalService
from coffer.domain.agent.config import AgentConfig
from coffer.domain.memory.delivery import DELIVERY_CEILING_BYTES
from coffer.domain.resource import Resource

logger = logging.getLogger(__name__)

#: The ``event`` a channel turn's audited fire names; a hook fire names the
#: agent's own hook event instead.
CHANNEL_TURN_EVENT = "ChannelTurn"


def conversation_session(conversation_id: str) -> str:
    """The ledger's session id for a Coffer-driven conversation."""
    return f"conversation:{conversation_id}"


class AgentRows(Protocol):
    async def list(self) -> Sequence[Resource]: ...


class FiredRecorder(Protocol):
    async def record_fired(
        self, agent_uid: str, details: dict[str, object] | None = None
    ) -> object: ...


class TurnRetrieval:
    """Composes one channel turn's memory and audits what it brought in."""

    def __init__(
        self,
        retrieval: RetrievalService,
        delivery: FiredRecorder,
        agents: AgentRows,
        memory: MemoryPort,
    ) -> None:
        self._retrieval = retrieval
        self._delivery = delivery
        self._agents = agents
        self._memory = memory

    async def _agent_uid(self, agent_key: str) -> str | None:
        """The agent a fire is audited against: of the registered agents of this
        type, an enabled one — a disabled agent is not the one answering."""
        for row in await self._agents.list():
            if not row.enabled:
                continue
            try:
                cfg = AgentConfig.model_validate(row.config)
            except ValueError:
                continue
            if cfg.type.value == agent_key:
                return row.uid
        return None

    async def _record(self, agent_key: str, details: dict[str, object]) -> None:
        agent_uid = await self._agent_uid(agent_key)
        if agent_uid is None:
            logger.warning("memory.turn_retrieval.no_agent; agent_key=%s", agent_key)
            return
        await self._delivery.record_fired(agent_uid, {**details, "event": CHANNEL_TURN_EVENT})

    async def index_for_turn(self, *, agent_key: str, cwd: str, conversation_id: str) -> str | None:
        """The index for this turn's system prompt, or ``None`` for nothing —
        an empty memory header is worse than none."""
        # The hook's own ceiling: this is the same payload, and a turn must not carry
        # more than an agent's hook would be allowed to.
        composed = await compose_context(
            self._memory, cwd=cwd, ceiling_bytes=DELIVERY_CEILING_BYTES
        )
        # A session start is audited whether or not there was anything to deliver,
        # exactly as the hook records it ("Audit every delivery fire").
        await self._record(
            agent_key,
            {
                "moment": MOMENT_SESSION_START,
                "session_id": conversation_session(conversation_id),
            },
        )
        return composed.text or None

    async def for_turn(
        self, *, agent_key: str, cwd: str, prompt: str, conversation_id: str
    ) -> str | None:
        """The notes this prompt names that the conversation was not given yet,
        as the text to add to the turn, or ``None`` for nothing."""
        session_id = conversation_session(conversation_id)
        got = await self._retrieval.retrieve(cwd=cwd, prompt=prompt, session_id=session_id)
        if not got.text:
            return None
        await self._record(
            agent_key,
            {"moment": MOMENT_PROMPT, "session_id": session_id, "notes": list(got.notes)},
        )
        return got.text


__all__ = ["CHANNEL_TURN_EVENT", "TurnRetrieval", "conversation_session"]
