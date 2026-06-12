"""BuiltinAgentProvider — the ``AgentProvider`` for Coffer's built-in agent.

This is the one provider registered in the agent-provider registry in v1. It
adapts Coffer's built-in LangGraph agent to the platform seam:

- ``init_conversation`` reads the built-in agent's only configuration — an
  optional ``model_id`` — out of ``agent_config`` and stores it on the
  conversation's ``model_id`` column. An invalid ``model_id`` is rejected.
- ``build_adapter`` resolves the conversation's model (raising
  ``NoModelConfigured`` when none exists), builds the LangChain model, fetches
  the skill catalogue, assembles the system prompt, and returns a per-turn
  ``LangGraphBuiltinAgent``.
- ``on_conversation_deleted`` is a no-op — the built-in agent's only
  per-conversation state is the ``model_id`` column, removed with the row.
- ``availability`` is always ``True``; a conversation created with no model
  surfaces the no-model state at turn time, not in the picker.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from coffer.application.chat.model_service import ModelService
from coffer.application.chat.ports import AgentAdapter, ToolGateway
from coffer.application.chat.service import ConversationRepo
from coffer.application.chat.system_prompt import SkillEntry, build_system_prompt
from coffer.domain.chat.model import ModelConfig
from coffer.domain.errors import (
    AgentConfigRejected,
    ConversationNotFound,
    ModelNotFound,
    NoModelConfigured,
)
from coffer.infrastructure.chat.langchain_models import build_chat_model
from coffer.infrastructure.chat.langgraph_agent import (
    DEFAULT_RECURSION_LIMIT,
    LangGraphBuiltinAgent,
)

log = logging.getLogger(__name__)


class BuiltinAgentProvider:
    """The ``AgentProvider`` for Coffer's built-in "Coffer Assistant" agent."""

    agent_key = "builtin"

    def __init__(
        self,
        *,
        model_service: ModelService,
        conversations: ConversationRepo,
        tool_gateway: ToolGateway,
        credential_resolver: Callable[[str], str],
        recursion_limit: int = DEFAULT_RECURSION_LIMIT,
    ) -> None:
        self._models = model_service
        self._conversations = conversations
        self._tool_gateway = tool_gateway
        self._credential_resolver = credential_resolver
        self._recursion_limit = recursion_limit

    # ------------------------------------------------------------------
    # AgentProvider protocol
    # ------------------------------------------------------------------

    async def init_conversation(self, conversation_id: str, agent_config: dict[str, Any]) -> None:
        """Validate + store the built-in agent's per-conversation config.

        The built-in agent's configuration is an optional ``model_id``. When
        present it must reference a registered model; it is stored on the
        conversation's ``model_id`` column. Absent, the conversation uses the
        default model.
        """
        raw_model_id = agent_config.get("model_id")
        if raw_model_id is None:
            return
        if not isinstance(raw_model_id, str):
            raise AgentConfigRejected(
                reason="invalid_model_id",
                message="agent_config.model_id must be a string",
            )
        try:
            await self._models.get(raw_model_id)
        except ModelNotFound as exc:
            raise AgentConfigRejected(
                reason="model_not_found",
                message=f"agent_config.model_id references no registered model: {raw_model_id!r}",
            ) from exc
        await self._conversations.set_model(conversation_id, raw_model_id)

    async def build_adapter(self, conversation_id: str) -> AgentAdapter:
        """Build a configured ``LangGraphBuiltinAgent`` for one turn.

        Raises ``NoModelConfigured`` when the conversation resolves to no model.
        """
        conv = await self._conversations.get(conversation_id)
        if conv is None:
            raise ConversationNotFound(conversation_id)

        model = await self._resolve_model(conv.model_id)
        lc_model = build_chat_model(model, self._credential_resolver)

        skills_data = await self._tool_gateway.call_tool("coffer__list_skills", {})
        system_prompt = build_system_prompt(_parse_skill_catalogue(skills_data))

        return LangGraphBuiltinAgent(
            lc_model=lc_model,
            tool_gateway=self._tool_gateway,
            system_prompt=system_prompt,
            model_id=model.id,
            recursion_limit=self._recursion_limit,
        )

    async def on_conversation_deleted(self, conversation_id: str) -> None:
        """No per-conversation state to clean up beyond the deleted row."""
        return

    async def availability(self) -> bool:
        """The built-in agent can always be picked."""
        return True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _resolve_model(self, model_id: str | None) -> ModelConfig:
        """Resolve the model for a turn: the override, else the default."""
        if model_id is not None:
            return await self._models.get(model_id)  # ModelNotFound if deleted
        default = await self._models.get_default()
        if default is None:
            raise NoModelConfigured()
        return default


# ---------------------------------------------------------------------------
# Skill catalogue parsing
# ---------------------------------------------------------------------------


def _parse_skill_catalogue(data: dict[str, Any]) -> list[SkillEntry]:
    """Parse the ``coffer__list_skills`` tool response into ``SkillEntry`` objects."""
    skills_raw = data.get("skills", [])
    result: list[SkillEntry] = []
    if isinstance(skills_raw, list):
        for item in skills_raw:
            if isinstance(item, dict):
                name = item.get("name", "")
                description = item.get("description", "")
                if name:
                    result.append(SkillEntry(name=str(name), description=str(description)))
    return result


__all__ = ["BuiltinAgentProvider"]
