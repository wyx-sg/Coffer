"""``cursor-agent``-backed provider — ``AgentProvider`` wrapping ``CursorRunAdapter``.

Mirrors :class:`OpencodeProvider`: validates and stores the working directory on
``init_conversation``, constructs a :class:`CursorRunAdapter` on
``build_adapter``, and reports binary availability via the injected ``which``
seam. The ``spawn`` seam lets tests inject a fake process without a real
``cursor-agent`` binary.

Unlike Codex / opencode / Hermes, cursor is **locked to Cursor's own backend and
uses Cursor's own auth** (``cursor-agent login`` / ``CURSOR_API_KEY``). Coffer
therefore projects NO connection into it and injects NO ``COFFER_PROVIDER_KEY``:
this provider has no ``resolve_key`` seam and passes no custom env — the
subprocess inherits the daemon env unchanged (like :class:`ClaudeSdkProvider`).
This is the provider-projection-N/A gap (ADR-040 capability matrix).
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
from coffer.infrastructure.chat.cursor_agent import CursorRunAdapter
from coffer.infrastructure.chat.cursor_run import CursorSpawner, default_spawn
from coffer.infrastructure.chat.default_workspace import default_workspace_dir
from coffer.infrastructure.chat.transcribe import default_transcriber


class CursorProvider:
    """``AgentProvider`` for the ``cursor-agent``-backed agent (``agent_key="cursor"``).

    Constructs a ``CursorRunAdapter`` per turn; the ``spawn`` seam lets tests
    inject a fake without a real ``cursor-agent`` binary. No ``resolve_key`` /
    env injection: cursor uses its own auth (see the module docstring).
    """

    agent_key = "cursor"
    _binary = "cursor-agent"

    def __init__(
        self,
        *,
        conversations: ConversationRepo,
        spawn: CursorSpawner | None = None,
        which: Any = shutil.which,
    ) -> None:
        self._conversations = conversations
        self._spawn: CursorSpawner = spawn or default_spawn
        self._which = which

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
        # Cursor binds no model (it uses the account default on its own backend),
        # so a chat-chosen ``model`` is intentionally NOT stored or projected.
        config = AgentConfig(cwd=str(resolved))
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

        return CursorRunAdapter(
            cwd=config.cwd,
            resume_session=config.session_id,
            # No custom env: cursor uses its own auth, so the subprocess inherits
            # the daemon env unchanged (the provider-projection-N/A gap).
            env=None,
            on_session=_save_session,
            spawn=self._spawn,
            binary=self._binary,
            # cursor-agent cannot hear audio; a voice attachment is transcribed to
            # text by the best local engine available here (ADR-039).
            transcriber=default_transcriber(),
        )

    async def on_conversation_deleted(self, conversation_id: str) -> None:
        return

    async def availability(self) -> bool:
        return self._which(self._binary) is not None


__all__ = ["CursorProvider"]
