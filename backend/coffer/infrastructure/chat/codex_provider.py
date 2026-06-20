"""App-server-backed Codex provider — ``AgentProvider`` wrapping ``CodexAppServerAdapter``.

Mirrors ``claude_sdk_provider.py`` (which wraps ``ClaudeSdkAgentAdapter``):
validates and stores the working directory on ``init_conversation``, constructs a
``CodexAppServerAdapter`` on ``build_adapter``, and reports binary availability
via the injected ``which`` seam.  The ``session_factory`` seam lets tests inject a
fake without a real ``codex`` binary (no subprocess needed).
"""

from __future__ import annotations

import pathlib
import shutil
from typing import Any

from coffer.application.chat.ports import AgentAdapter
from coffer.application.chat.service import ConversationRepo
from coffer.domain.errors import AgentConfigRejected, ConversationNotFound
from coffer.infrastructure.chat.codex_agent import CodexAppServerAdapter
from coffer.infrastructure.chat.codex_app_server import (
    AppServerSessionFactory,
    default_app_server_session,
)
from coffer.infrastructure.chat.default_workspace import default_workspace_dir


class CodexAppServerProvider:
    """``AgentProvider`` for the app-server-backed Codex agent (``agent_key="codex"``).

    Constructs a ``CodexAppServerAdapter`` per turn; the ``session_factory`` seam
    lets tests inject a fake without a real ``codex`` binary.
    """

    agent_key = "codex"
    _binary = "codex"

    def __init__(
        self,
        *,
        conversations: ConversationRepo,
        session_factory: AppServerSessionFactory | None = None,
        which: Any = shutil.which,
    ) -> None:
        self._conversations = conversations
        self._session_factory: AppServerSessionFactory = (
            session_factory or default_app_server_session
        )
        self._which = which

    async def init_conversation(self, conversation_id: str, agent_config: dict[str, Any]) -> None:
        cwd = agent_config.get("cwd")
        if not isinstance(cwd, str) or not cwd.strip():
            # No working directory given — fall back to the Coffer-managed
            # workspace rather than fail the turn (parity with the SDK provider).
            cwd = default_workspace_dir()
        if not pathlib.Path(cwd).expanduser().is_dir():
            raise AgentConfigRejected(
                reason="cwd_not_a_directory",
                message=f"agent_config.cwd is not an existing directory: {cwd!r}",
            )
        stored: dict[str, Any] = {"cwd": str(pathlib.Path(cwd).expanduser())}
        if isinstance(agent_config.get("model"), str):
            stored["model"] = agent_config["model"]
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

        return CodexAppServerAdapter(
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


__all__ = ["CodexAppServerProvider"]
