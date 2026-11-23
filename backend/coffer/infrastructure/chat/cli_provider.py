"""``AgentProvider`` for an agent driven through its one-shot command line
(:mod:`coffer.infrastructure.chat.cli_turn`): OpenCode, Cursor and DeepSeek
Harness.

The same contract as the Claude Code and Codex providers: the working directory
is checked and stored when a conversation starts, and each turn is built on the
type's one managed agent, with its config directory, the user's PATH, the
turn's token for the turn-scoped tools, and the system context (memories,
channel note, model note) every provider owes its agent.
"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

from coffer.application.chat import turn_tokens
from coffer.application.chat.ports import AgentAdapter
from coffer.application.chat.service import ConversationRepo
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.errors import AgentConfigRejected, ConversationNotFound
from coffer.infrastructure.chat.adapter_support import (
    MEMORY_IN_PROMPT_ENV,
    ChannelNoteResolver,
    HomeEnvResolver,
    ManagedCheck,
    MemoryResolver,
    ModelLister,
    compose_system_context,
    require_managed,
)
from coffer.infrastructure.chat.cli_turn import CliAgent, CliTurnAdapter
from coffer.infrastructure.chat.default_workspace import default_workspace_dir
from coffer.infrastructure.chat.transcribe import Transcriber
from coffer.infrastructure.platform.user_path import user_path_env, which_on_user_path

TranscriberFactory = Callable[[], Awaitable["Transcriber | None"]]


class CliProvider:
    """One agent type, one CLI. ``which`` finds its program on the user's PATH."""

    def __init__(
        self,
        *,
        agent: CliAgent,
        program: str,
        conversations: ConversationRepo,
        which: Any = which_on_user_path,
        list_models: ModelLister | None = None,
        transcriber_factory: TranscriberFactory | None = None,
        resolve_channel: ChannelNoteResolver | None = None,
        resolve_home_env: HomeEnvResolver | None = None,
        is_managed: ManagedCheck | None = None,
        resolve_memory: MemoryResolver | None = None,
    ) -> None:
        self._agent = agent
        self.agent_key = agent.agent_key
        self._program = program
        self._conversations = conversations
        self._which = which
        self._list_models = list_models
        self._transcriber_factory = transcriber_factory
        self._resolve_channel = resolve_channel
        self._resolve_home_env = resolve_home_env
        self._is_managed = is_managed
        self._resolve_memory = resolve_memory

    async def init_conversation(self, conversation_id: str, agent_config: dict[str, Any]) -> None:
        cwd = agent_config.get("cwd")
        if not isinstance(cwd, str) or not cwd.strip():
            cwd = default_workspace_dir()
        resolved = pathlib.Path(cwd).expanduser()
        if not resolved.is_dir():
            raise AgentConfigRejected(
                reason="cwd_not_a_directory",
                message=f"agent_config.cwd is not an existing directory: {cwd!r}",
            )
        model = agent_config.get("model")
        await self._conversations.set_agent_config(
            conversation_id,
            AgentConfig(cwd=str(resolved), model=model if isinstance(model, str) else None),
        )

    async def build_adapter(self, conversation_id: str) -> AgentAdapter:
        await require_managed(self._is_managed, self.agent_key)
        conv = await self._conversations.get(conversation_id)
        if conv is None:
            raise ConversationNotFound(conversation_id)
        config = await self._conversations.get_agent_config(conversation_id)
        if not config.cwd:
            raise AgentConfigRejected(
                reason="invalid_cwd",
                message="conversation has no working directory configured",
            )
        binary = self._which(self._program)
        if binary is None:
            raise AgentConfigRejected(
                reason="agent_not_installed",
                message=f"{self._program} is not on this Mac's PATH",
            )

        async def _save_session(session_id: str) -> None:
            latest = await self._conversations.get_agent_config(conversation_id)
            await self._conversations.set_agent_config(
                conversation_id, replace(latest, session_id=session_id)
            )

        overrides: dict[str, str] = (
            dict(await self._resolve_home_env()) if self._resolve_home_env else {}
        )
        overrides.update(turn_tokens.turn_env(conversation_id))
        overrides.update(await asyncio.to_thread(user_path_env))
        memory = await self._resolve_memory(config.cwd) if self._resolve_memory else ""
        if memory:
            overrides[MEMORY_IN_PROMPT_ENV] = "1"
        system_context = await compose_system_context(
            agent_key=self.agent_key,
            channel_uid=conv.channel_uid or "",
            model=config.model,
            list_models=self._list_models,
            resolve_channel=self._resolve_channel,
            conversation_id=conversation_id,
            memory=memory,
        )
        transcriber = await self._transcriber_factory() if self._transcriber_factory else None
        return CliTurnAdapter(
            agent=self._agent,
            binary=binary,
            cwd=config.cwd,
            env=overrides,
            model=config.model,
            resume_session=config.session_id,
            on_session=_save_session,
            system_context=system_context,
            transcriber=transcriber,
        )

    async def on_conversation_deleted(self, conversation_id: str) -> None:
        return

    async def availability(self) -> bool:
        if self._which(self._program) is None:
            return False
        return self._is_managed is None or await self._is_managed()


__all__ = ["CliProvider"]
