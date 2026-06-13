"""SDK-backed Claude provider — ``AgentProvider`` wrapping ``ClaudeSdkAgentAdapter``.

Mirrors ``cli_providers.py`` (which wraps ``CliAgentAdapter``): validates and
stores the working directory on ``init_conversation``, constructs a
``ClaudeSdkAgentAdapter`` on ``build_adapter``, and reports binary availability
via the injected ``which`` seam.  The ``session_factory`` seam lets tests inject
a fake without a real ``claude`` binary (no network/subprocess needed).
"""

from __future__ import annotations

import pathlib
import shutil
from typing import Any

from coffer.application.chat.ports import AgentAdapter
from coffer.application.chat.service import ConversationRepo
from coffer.domain.errors import AgentConfigRejected, ConversationNotFound
from coffer.infrastructure.chat.claude_sdk_agent import (
    ClaudeSdkAgentAdapter,
    SdkSessionFactory,
    default_session_factory,
)


class ClaudeSdkProvider:
    """``AgentProvider`` for the SDK-backed Claude agent (``agent_key="claude_code"``).

    Replaces ``ClaudeCodeProvider`` in the composition root: same ``agent_key``,
    same ``init_conversation`` / ``build_adapter`` contract, but constructs a
    ``ClaudeSdkAgentAdapter`` instead of a ``CliAgentAdapter``.  The
    ``session_factory`` seam lets tests inject a fake without a real ``claude``
    binary.
    """

    agent_key = "claude_code"
    _binary = "claude"

    def __init__(
        self,
        *,
        conversations: ConversationRepo,
        session_factory: SdkSessionFactory | None = None,
        which: Any = shutil.which,
    ) -> None:
        self._conversations = conversations
        self._session_factory: SdkSessionFactory = session_factory or default_session_factory
        self._which = which

    async def init_conversation(self, conversation_id: str, agent_config: dict[str, Any]) -> None:
        cwd = agent_config.get("cwd")
        if not isinstance(cwd, str) or not cwd.strip():
            raise AgentConfigRejected(
                reason="invalid_cwd",
                message="agent_config.cwd (a working directory path) is required",
            )
        if not pathlib.Path(cwd).expanduser().is_dir():
            raise AgentConfigRejected(
                reason="cwd_not_a_directory",
                message=f"agent_config.cwd is not an existing directory: {cwd!r}",
            )
        stored: dict[str, Any] = {"cwd": str(pathlib.Path(cwd).expanduser())}
        if isinstance(agent_config.get("permission_mode"), str):
            stored["permission_mode"] = agent_config["permission_mode"]
        await self._conversations.set_agent_config(conversation_id, stored)

    async def build_adapter(self, conversation_id: str) -> AgentAdapter:
        conv = await self._conversations.get(conversation_id)
        if conv is None:
            raise ConversationNotFound(conversation_id)
        config = await self._conversations.get_agent_config(conversation_id)
        cwd = config.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            raise AgentConfigRejected(
                reason="invalid_cwd",
                message="conversation has no working directory configured",
            )

        async def _save_session(session_id: str) -> None:
            latest = await self._conversations.get_agent_config(conversation_id)
            latest["session_id"] = session_id
            await self._conversations.set_agent_config(conversation_id, latest)

        return ClaudeSdkAgentAdapter(
            cwd=cwd,
            resume_session=config.get("session_id"),
            extra=config,
            session_factory=self._session_factory,
            on_session=_save_session,
        )

    async def on_conversation_deleted(self, conversation_id: str) -> None:
        return

    async def availability(self) -> bool:
        return self._which(self._binary) is not None


__all__ = ["ClaudeSdkProvider"]
