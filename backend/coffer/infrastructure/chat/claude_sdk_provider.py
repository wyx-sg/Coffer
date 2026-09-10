"""SDK-backed Claude provider — ``AgentProvider`` wrapping ``ClaudeSdkAgentAdapter``.

Validates and stores the working directory on ``init_conversation``, constructs a
``ClaudeSdkAgentAdapter`` on ``build_adapter``, and reports binary availability
via the injected ``which`` seam.  The ``session_factory`` seam lets tests inject
a fake without a real ``claude`` binary (no network/subprocess needed).
"""

from __future__ import annotations

import pathlib
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

from coffer.application.chat.ports import AgentAdapter
from coffer.application.chat.service import ConversationRepo
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.errors import AgentConfigRejected, ConversationNotFound
from coffer.infrastructure.chat.adapter_support import (
    channel_system_context,
    model_system_context,
)
from coffer.infrastructure.chat.claude_sdk_agent import (
    ClaudeSdkAgentAdapter,
    SdkSessionFactory,
    default_session_factory,
)
from coffer.infrastructure.chat.default_workspace import default_workspace_dir
from coffer.infrastructure.chat.document_extract import default_document_extractor
from coffer.infrastructure.chat.transcribe import Transcriber

#: The model ids this agent can be put on, looked up per turn. A narrow callable
#: rather than the application catalogue service itself, so infrastructure keeps
#: no dependency on an application type it would only read one list from.
ModelLister = Callable[[str], Awaitable[list[str]]]

#: Builds the transcriber for one turn, or ``None`` to leave audio untouched.
#: Resolved per turn so designating (or clearing) the internal connection takes
#: effect without a daemon restart. ``None`` here means the composition root
#: wired no transcription at all.
TranscriberFactory = Callable[[], Awaitable["Transcriber | None"]]


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
        list_models: ModelLister | None = None,
        transcriber_factory: TranscriberFactory | None = None,
    ) -> None:
        self._conversations = conversations
        self._session_factory: SdkSessionFactory = session_factory or default_session_factory
        self._which = which
        # None ⇒ the model note lists no ids (still tells the agent WHICH model
        # it is on, which is the part it otherwise gets wrong).
        self._list_models = list_models
        # None ⇒ voice is never transcribed and the audio file reaches the agent
        # as-is. That is the default: nothing leaves the machine unasked.
        self._transcriber_factory = transcriber_factory

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

        # Two system-prompt appends, joined into one:
        # - a channel-originated conversation drives the agent from a phone chat,
        #   so tell it so (concise replies, no clickable dialogs);
        # - EVERY conversation gets the model note, because the agent cannot see
        #   which model Coffer put it on and otherwise invents an answer.
        parts: list[str] = []
        if conv.channel_name:
            parts.append(channel_system_context(conv.channel_name))
        available = await self._list_models(self.agent_key) if self._list_models else []
        parts.append(model_system_context(config.model, available))
        system_context = "\n\n".join(parts)

        return ClaudeSdkAgentAdapter(
            cwd=config.cwd,
            resume_session=config.session_id,
            extra={"model": config.model},
            session_factory=self._session_factory,
            on_session=_save_session,
            system_context=system_context,
            # Claude cannot hear audio. A voice attachment is transcribed by the
            # user's configured connection, or handed over untouched when there
            # is none (spec 009 FR-022).
            transcriber=await self._transcriber(),
            # A document (PDF/office file) is text-extracted so it reaches the
            # agent as text rather than a vision/binary block (FR-030).
            document_extractor=default_document_extractor(),
        )

    async def on_conversation_deleted(self, conversation_id: str) -> None:
        return

    async def _transcriber(self) -> Transcriber | None:
        if self._transcriber_factory is None:
            return None
        return await self._transcriber_factory()

    async def availability(self) -> bool:
        return self._which(self._binary) is not None


__all__ = ["ClaudeSdkProvider", "ModelLister"]
