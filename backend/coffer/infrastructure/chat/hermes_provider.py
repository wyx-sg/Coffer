"""ACP-backed hermes provider — ``AgentProvider`` wrapping ``HermesAcpAdapter``.

Mirrors :class:`OpencodeProvider` / :class:`CodexAppServerProvider`: validates and
stores the working directory on ``init_conversation``, constructs a
:class:`HermesAcpAdapter` on ``build_adapter``, and reports binary availability
via the injected ``which`` seam. Like Codex, hermes reads Coffer's projected API
key from an env var NAMED by config (its ``config.yaml`` ``providers.coffer`` block
carries ``key_env: COFFER_PROVIDER_KEY``, the Codex-style ``env_key`` analogue —
not opencode's ``{env:...}`` interpolation), so the active connection's key is
injected into the subprocess env per turn. The
``session_factory`` seam lets tests inject a fake ACP peer without a real
``hermes`` binary.
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
from coffer.domain.errors import AgentConfigRejected, ConversationNotFound
from coffer.domain.provider.projection import CODEX_ENV_KEY
from coffer.infrastructure.chat.default_workspace import default_workspace_dir
from coffer.infrastructure.chat.hermes_acp import AcpSessionFactory, default_hermes_acp_session
from coffer.infrastructure.chat.hermes_agent import HermesAcpAdapter
from coffer.infrastructure.chat.transcribe import default_transcriber

#: Resolve the active connection's decrypted API key, or ``None`` when no Coffer
#: connection is active for hermes (it then runs on its own configured provider).
KeyResolver = Callable[[], Awaitable[str | None]]


class HermesProvider:
    """``AgentProvider`` for the ACP-backed hermes agent (``agent_key="hermes"``).

    Constructs a ``HermesAcpAdapter`` per turn; the ``session_factory`` seam lets
    tests inject a fake ACP peer without a real ``hermes`` binary.
    """

    agent_key = "hermes"
    _binary = "hermes"

    def __init__(
        self,
        *,
        conversations: ConversationRepo,
        session_factory: AcpSessionFactory | None = None,
        which: Any = shutil.which,
        resolve_key: KeyResolver | None = None,
    ) -> None:
        self._conversations = conversations
        self._session_factory: AcpSessionFactory = session_factory or default_hermes_acp_session
        self._which = which
        # Resolves the active connection's key for COFFER_PROVIDER_KEY injection
        # (ADR-032 env_key seam). ``None`` → no injection, hermes inherits the
        # daemon env and uses its own configured provider/login.
        self._resolve_key = resolve_key

    async def init_conversation(self, conversation_id: str, agent_config: dict[str, Any]) -> None:
        cwd = agent_config.get("cwd")
        if not isinstance(cwd, str) or not cwd.strip():
            # No working directory given — fall back to the Coffer-managed
            # workspace rather than fail the turn (parity with the other providers).
            cwd = default_workspace_dir()
        resolved = pathlib.Path(cwd).expanduser()
        if not resolved.is_dir():
            raise AgentConfigRejected(
                reason="cwd_not_a_directory",
                message=f"agent_config.cwd is not an existing directory: {cwd!r}",
            )
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

        # Inject the active connection's key as COFFER_PROVIDER_KEY (the env var
        # the projected config.yaml provider block references). MERGE with
        # os.environ — create_subprocess_exec REPLACES the environment, so a bare
        # {KEY: ...} would strip PATH etc.
        env: dict[str, str] | None = None
        if self._resolve_key is not None:
            key = await self._resolve_key()
            if key:
                env = {**os.environ, CODEX_ENV_KEY: key}

        return HermesAcpAdapter(
            cwd=config.cwd,
            resume_session=config.session_id,
            extra={"model": config.model},
            session_factory=self._session_factory,
            on_session=_save_session,
            env=env,
            # hermes cannot hear audio; a voice attachment is transcribed to text
            # by the best local engine available here (ADR-039).
            transcriber=default_transcriber(),
        )

    async def on_conversation_deleted(self, conversation_id: str) -> None:
        return

    async def availability(self) -> bool:
        return self._which(self._binary) is not None


__all__ = ["HermesProvider"]
