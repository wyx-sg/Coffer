"""Prompt-time retrieval for a turn Coffer drives itself (spec memory "Retrieve
the notes a prompt names for a channel turn").

A channel-driven turn runs no hook of Coffer's: Coffer spawns the agent and
owns its context (spec memory "Deliver to channel turns through the system
prompt"). So the per-prompt half of delivery is done here, by the same
``RetrievalService`` the ``UserPromptSubmit`` hook answers through — the same
ranking, floor, top three, 1.5 KB ceiling and per-session ledger — keyed on
the conversation, and audited as a ``prompt`` fire of the answering agent just
as a hook fire is (spec memory "Audit every delivery fire").
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol

from coffer.application.memory.hook_service import MOMENT_PROMPT
from coffer.application.memory.retrieval import RetrievalService
from coffer.domain.agent.config import AgentConfig
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
    """Ranks one channel turn's prompt and audits what it brought in."""

    def __init__(
        self, retrieval: RetrievalService, delivery: FiredRecorder, agents: AgentRows
    ) -> None:
        self._retrieval = retrieval
        self._delivery = delivery
        self._agents = agents

    async def _agent_uid(self, agent_key: str) -> str | None:
        for row in await self._agents.list():
            try:
                cfg = AgentConfig.model_validate(row.config)
            except ValueError:
                continue
            if cfg.type.value == agent_key:
                return row.uid
        return None

    async def for_turn(
        self, *, agent_key: str, cwd: str, prompt: str, conversation_id: str
    ) -> str | None:
        """The notes this prompt names that the conversation was not given yet,
        as the text to add to the turn, or ``None`` for nothing."""
        session_id = conversation_session(conversation_id)
        got = await self._retrieval.retrieve(cwd=cwd, prompt=prompt, session_id=session_id)
        if not got.text:
            return None
        agent_uid = await self._agent_uid(agent_key)
        if agent_uid is None:
            logger.warning("memory.turn_retrieval.no_agent; agent_key=%s", agent_key)
        else:
            await self._delivery.record_fired(
                agent_uid,
                {
                    "moment": MOMENT_PROMPT,
                    "session_id": session_id,
                    "event": CHANNEL_TURN_EVENT,
                    "notes": list(got.notes),
                },
            )
        return got.text


__all__ = ["CHANNEL_TURN_EVENT", "TurnRetrieval", "conversation_session"]
