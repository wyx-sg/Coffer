"""SDK-backed Claude provider — ``AgentProvider`` wrapping ``ClaudeSdkAgentAdapter``.

Validates and stores the working directory on ``init_conversation``, constructs a
``ClaudeSdkAgentAdapter`` on ``build_adapter``, and reports binary availability
via the injected ``which`` seam.  The ``session_factory`` seam lets tests inject
a fake without a real ``claude`` binary (no network/subprocess needed).
"""

from __future__ import annotations

import pathlib
import shutil
from dataclasses import replace
from typing import Any

from coffer.application.chat.ports import AgentAdapter
from coffer.application.chat.service import ConversationRepo
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.errors import AgentConfigRejected, ConversationNotFound
from coffer.infrastructure.chat.adapter_support import channel_system_context
from coffer.infrastructure.chat.claude_sdk_agent import (
    ClaudeSdkAgentAdapter,
    SdkSessionFactory,
    default_session_factory,
)
from coffer.infrastructure.chat.default_workspace import default_workspace_dir
from coffer.infrastructure.chat.document_extract import default_document_extractor
from coffer.infrastructure.chat.transcribe import default_transcriber


class ClaudeSdkProvider:
    """``AgentProvider`` for the SDK-backed Claude agent (``agent_key="claude_code"``).

    Constructs a ``ClaudeSdkAgentAdapter`` per turn; the ``session_factory`` seam
    lets tests inject a fake without a real ``claude`` binary.
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
            # No working directory given (a channel without a workspace, or a
            # chat draft now that the per-turn picker is gone). Fall back to the
            # Coffer-managed workspace rather than fail the turn silently.
            cwd = default_workspace_dir()
        resolved = pathlib.Path(cwd).expanduser()
        if not resolved.is_dir():
            raise AgentConfigRejected(
                reason="cwd_not_a_directory",
                message=f"agent_config.cwd is not an existing directory: {cwd!r}",
            )
        # Persist the model so a chat-chosen model reaches the SDK; without this
        # the option was always None and the CLI always picked the model itself.
        model = agent_config.get("model")
        config = AgentConfig(cwd=str(resolved), model=model if isinstance(model, str) else None)
        await self._conversations.set_agent_config(conversation_id, config)

    async def build_adapter(self, conversation_id: str) -> AgentAdapter:
        conv = await self._conversations.get(conversation_id)
        if conv is None:
            raise ConversationNotFound(conversation_id)
        config = await self._conversations.get_agent_config(conversation_id)
        if not config.cwd:
            raise AgentConfigRejected(
                reason="invalid_cwd",
                message="conversation has no working directory configured",
            )

        async def _save_session(session_id: str) -> None:
            latest = await self._conversations.get_agent_config(conversation_id)
            await self._conversations.set_agent_config(
                conversation_id, replace(latest, session_id=session_id)
            )

        # A channel-originated conversation drives the agent from a phone chat —
        # tell it so (concise replies, no clickable dialogs) via a system-prompt
        # append. Non-channel (web UI) turns leave the prompt untouched.
        system_context = channel_system_context(conv.channel_name) if conv.channel_name else None

        return ClaudeSdkAgentAdapter(
            cwd=config.cwd,
            resume_session=config.session_id,
            extra={"model": config.model},
            session_factory=self._session_factory,
            on_session=_save_session,
            system_context=system_context,
            # Claude cannot hear audio; a voice attachment is transcribed to text
            # by the best local engine available here (ADR-039).
            transcriber=default_transcriber(),
            # A document (PDF/office file) is text-extracted so it reaches the
            # agent as text rather than a vision/binary block (FR-030).
            document_extractor=default_document_extractor(),
        )

    async def on_conversation_deleted(self, conversation_id: str) -> None:
        return

    async def availability(self) -> bool:
        return self._which(self._binary) is not None


__all__ = ["ClaudeSdkProvider"]
