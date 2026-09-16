"""App-server-backed Codex provider — ``AgentProvider`` wrapping ``CodexAppServerAdapter``.

Mirrors ``claude_sdk_provider.py`` (which wraps ``ClaudeSdkAgentAdapter``):
validates and stores the working directory on ``init_conversation``, constructs a
``CodexAppServerAdapter`` on ``build_adapter``, and reports binary availability
via the injected ``which`` seam.  The ``session_factory`` seam lets tests inject a
fake without a real ``codex`` binary (no subprocess needed).
"""

from __future__ import annotations

import os
import pathlib
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

from coffer.application.chat.ports import AgentAdapter
from coffer.application.chat.service import ConversationRepo
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.errors import AgentConfigRejected, ConversationNotFound
from coffer.domain.connection import CODEX_ENV_KEY
from coffer.infrastructure.chat.adapter_support import (
    MemoryContextComposer,
    ModelLister,
    compose_system_context,
)
from coffer.infrastructure.chat.codex_agent import CodexAppServerAdapter
from coffer.infrastructure.chat.codex_app_server import (
    AppServerSessionFactory,
    default_app_server_session,
)
from coffer.infrastructure.chat.default_workspace import default_workspace_dir
from coffer.infrastructure.chat.document_extract import default_document_extractor
from coffer.infrastructure.chat.transcribe import Transcriber

#: Resolve the active openai connection's decrypted API key, or ``None`` when no
#: Coffer connection is active for Codex (it then runs on its own login).
KeyResolver = Callable[[], Awaitable[str | None]]


#: Builds the transcriber for one turn, or ``None`` to leave audio untouched.
#: Resolved per turn so designating (or clearing) the internal connection takes
#: effect without a daemon restart. ``None`` here means the composition root
#: wired no transcription at all.
TranscriberFactory = Callable[[], Awaitable["Transcriber | None"]]


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
        resolve_key: KeyResolver | None = None,
        transcriber_factory: TranscriberFactory | None = None,
        list_models: ModelLister | None = None,
        compose_memory_context: MemoryContextComposer | None = None,
    ) -> None:
        self._conversations = conversations
        self._session_factory: AppServerSessionFactory = (
            session_factory or default_app_server_session
        )
        self._which = which
        # Resolves the active openai connection's key for COFFER_PROVIDER_KEY
        # injection (the provider-switching env_key seam). ``None`` → no injection, codex
        # inherits the daemon env and uses its own login.
        self._resolve_key = resolve_key
        # None ⇒ voice is never transcribed and the audio file reaches the agent
        # as-is. That is the default: nothing leaves the machine unasked.
        self._transcriber_factory = transcriber_factory
        # The same two notes the SDK provider has always sent, plus the memory
        # digest. Codex sent none of them until the app-server's
        # ``developerInstructions`` field made it possible — so a Codex agent
        # answering a phone had no idea it was on one.
        self._list_models = list_models
        self._compose_memory_context = compose_memory_context

    async def init_conversation(self, conversation_id: str, agent_config: dict[str, Any]) -> None:
        cwd = agent_config.get("cwd")
        if not isinstance(cwd, str) or not cwd.strip():
            # No working directory given — fall back to the Coffer-managed
            # workspace rather than fail the turn (parity with the SDK provider).
            cwd = default_workspace_dir()
        resolved = pathlib.Path(cwd).expanduser()
        if not resolved.is_dir():
            raise AgentConfigRejected(
                reason="cwd_not_a_directory",
                message=f"agent_config.cwd is not an existing directory: {cwd!r}",
            )
        model = agent_config.get("model")
        effort = agent_config.get("effort")
        config = AgentConfig(
            cwd=str(resolved),
            model=model if isinstance(model, str) else None,
            # Codex's own reasoning level, accepted here so a conversation can
            # be created already set to one. Validated no more than the model
            # is: Codex owns the namespace and is what refuses a bad value.
            effort=effort if isinstance(effort, str) and effort.strip() else None,
        )
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

        # Inject the active openai connection's key as COFFER_PROVIDER_KEY (the
        # env var named by config.toml's ``env_key``). Codex reads the key from
        # there; without it it fails "Missing environment variable:
        # COFFER_PROVIDER_KEY". MERGE with os.environ — create_subprocess_exec
        # REPLACES the environment, so a bare {KEY: ...} would strip PATH etc.
        env: dict[str, str] | None = None
        if self._resolve_key is not None:
            key = await self._resolve_key()
            if key:
                env = {**os.environ, CODEX_ENV_KEY: key}

        system_context = await compose_system_context(
            agent_key=self.agent_key,
            channel_name=conv.channel_name or "",
            cwd=config.cwd,
            model=config.model,
            list_models=self._list_models,
            compose_memory=self._compose_memory_context,
        )

        return CodexAppServerAdapter(
            cwd=config.cwd,
            system_context=system_context,
            resume_session=config.session_id,
            extra={"model": config.model, "effort": config.effort},
            session_factory=self._session_factory,
            on_session=_save_session,
            env=env,
            # Codex cannot hear audio. A voice attachment is transcribed by the
            # user's configured connection, or handed over untouched when there
            # is none (spec channels FR-019).
            transcriber=await self._transcriber(),
            # Codex is path-native and cannot parse a binary PDF; a document is
            # text-extracted so it reaches the agent as text (FR-031).
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


__all__ = ["CodexAppServerProvider"]
