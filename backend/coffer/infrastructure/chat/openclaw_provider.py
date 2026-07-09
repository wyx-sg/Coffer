"""``openclaw agent``-backed provider — ``AgentProvider`` wrapping the adapter.

Mirrors :class:`OpencodeProvider` in shape, with two openclaw-specific
differences (ADR-044):

- **No cwd semantics.** openclaw is a personal-assistant gateway, not a
  repo-scoped coding CLI: ``openclaw agent`` has no cwd flag and every turn
  runs in the agent's own workspace (``agents.defaults.workspace``, default
  ``~/.openclaw/workspace``). ``init_conversation`` therefore IGNORES the
  conversation's ``cwd`` instead of validating it — a chat opened on a project
  still works, it just doesn't scope openclaw to that project.
- **No session discovery.** The upstream session is pinned by a Coffer-chosen
  ``--session-key`` derived from the conversation id, so nothing is parsed out
  of the stream and nothing is persisted per turn.

Like Codex/opencode/hermes, openclaw reads Coffer's projected API key from the
``COFFER_PROVIDER_KEY`` env var (its ``openclaw.json`` provider block persists
``"apiKey": "${COFFER_PROVIDER_KEY}"``), so the active connection's key is
injected into the subprocess env per turn; a missing env var is a startup
warning for openclaw, never an error (probe-verified on 2026.6.11).
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Awaitable, Callable
from typing import Any

from coffer.application.chat.ports import AgentAdapter
from coffer.application.chat.service import ConversationRepo
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.errors import ConversationNotFound
from coffer.domain.provider.projection import CODEX_ENV_KEY
from coffer.infrastructure.chat.default_workspace import default_workspace_dir
from coffer.infrastructure.chat.document_extract import default_document_extractor
from coffer.infrastructure.chat.openclaw_agent import OpenclawAgentAdapter
from coffer.infrastructure.chat.openclaw_run import OpenclawSpawner, default_spawn
from coffer.infrastructure.chat.transcribe import default_transcriber

#: Resolve the active connection's decrypted API key, or ``None`` when no Coffer
#: connection is active for openclaw (it then runs on its own configured
#: providers).
KeyResolver = Callable[[], Awaitable[str | None]]


def session_key_for(conversation_id: str) -> str:
    """The deterministic openclaw ``--session-key`` for a Coffer conversation.

    The same key always resumes the same upstream session (history under
    ``~/.openclaw/agents/<id>/sessions/``), so multi-turn continuity needs no
    discovered-session persistence.
    """
    return f"coffer-{conversation_id}"


class OpenclawProvider:
    """``AgentProvider`` for the ``openclaw agent``-backed agent (``agent_key="openclaw"``)."""

    agent_key = "openclaw"
    _binary = "openclaw"

    def __init__(
        self,
        *,
        conversations: ConversationRepo,
        spawn: OpenclawSpawner | None = None,
        which: Any = shutil.which,
        resolve_key: KeyResolver | None = None,
    ) -> None:
        self._conversations = conversations
        self._spawn: OpenclawSpawner = spawn or default_spawn
        self._which = which
        # Resolves the active connection's key for COFFER_PROVIDER_KEY injection
        # (ADR-032 env_key seam). ``None`` → no injection, openclaw inherits the
        # daemon env and uses its own configured providers.
        self._resolve_key = resolve_key

    async def init_conversation(self, conversation_id: str, agent_config: dict[str, Any]) -> None:
        # openclaw has NO cwd flag — it always runs in its own agent workspace,
        # so a supplied conversation cwd is deliberately ignored (not validated,
        # not stored): storing it would misrepresent where the turn runs.
        model = agent_config.get("model")
        config = AgentConfig(cwd=None, model=model if isinstance(model, str) else None)
        await self._conversations.set_agent_config(conversation_id, config)

    async def build_adapter(self, conversation_id: str) -> AgentAdapter:
        conv = await self._conversations.get(conversation_id)
        if conv is None:
            raise ConversationNotFound(conversation_id)
        config = await self._conversations.get_agent_config(conversation_id)

        # Inject the active connection's key as COFFER_PROVIDER_KEY (the env var
        # the projected openclaw.json provider block references). MERGE with
        # os.environ — create_subprocess_exec REPLACES the environment, so a bare
        # {KEY: ...} would strip PATH etc.
        env: dict[str, str] | None = None
        if self._resolve_key is not None:
            key = await self._resolve_key()
            if key:
                env = {**os.environ, CODEX_ENV_KEY: key}

        return OpenclawAgentAdapter(
            # PROCESS cwd only (openclaw ignores it for the turn itself); the
            # Coffer-managed workspace is a stable, always-existing directory.
            cwd=default_workspace_dir(),
            session_key=session_key_for(conversation_id),
            env=env,
            spawn=self._spawn,
            binary=self._binary,
            model=config.model,
            # openclaw's headless turn takes text; a voice attachment is
            # transcribed by the best local engine available here (ADR-039).
            transcriber=default_transcriber(),
            # A document is text-extracted so it reaches the agent as text
            # (FR-030) — the -m message cannot carry a binary PDF.
            document_extractor=default_document_extractor(),
        )

    async def on_conversation_deleted(self, conversation_id: str) -> None:
        return

    async def availability(self) -> bool:
        return self._which(self._binary) is not None


__all__ = ["OpenclawProvider", "session_key_for"]
