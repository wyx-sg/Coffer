"""SDK-backed Claude provider — ``AgentProvider`` wrapping ``ClaudeSdkAgentAdapter``.

Validates and stores the working directory on ``init_conversation``, constructs a
``ClaudeSdkAgentAdapter`` on ``build_adapter``, and reports binary availability
via the injected ``which`` seam.  The ``session_factory`` seam lets tests inject
a fake without a real ``claude`` binary (no network/subprocess needed).
"""

from __future__ import annotations

import pathlib
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

from coffer.application.chat import questions
from coffer.application.chat.ports import AgentAdapter
from coffer.application.chat.question_agents import asker_for
from coffer.application.chat.service import ConversationRepo
from coffer.domain.channel_turn import channel_turn_env
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.errors import AgentConfigRejected, ConversationNotFound
from coffer.infrastructure.chat.adapter_support import (
    ChannelNoteResolver,
    HomeEnvResolver,
    ManagedCheck,
    MemoryContextComposer,
    ModelLister,
    compose_system_context,
    require_managed,
)
from coffer.infrastructure.chat.claude_sdk_agent import (
    ClaudeSdkAgentAdapter,
    SdkSessionFactory,
    default_session_factory,
)
from coffer.infrastructure.chat.default_workspace import default_workspace_dir
from coffer.infrastructure.chat.document_extract import default_document_extractor
from coffer.infrastructure.chat.prompt_memory import MemoryRetriever, bind_prompt_memory
from coffer.infrastructure.chat.transcribe import Transcriber
from coffer.infrastructure.platform.user_path import which_on_user_path

#: The model ids this agent can be put on, looked up per turn. A narrow callable
#: rather than the application catalogue service itself, so infrastructure keeps
#: no dependency on an application type it would only read one list from.

#: The memory-context append a channel turn carries (spec memory "Deliver to
#: channel turns through the system prompt") arrives as a
#: ``MemoryContextComposer`` — a narrow callable, never
#: ``application.memory.context.compose_context`` imported here, so this layer
#: never reaches into the memory kind itself. The composition root builds the
#: real closure over ``MemoryService`` (``memory_turn_wiring.memory_context_composer``).

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
        which: Any = which_on_user_path,
        list_models: ModelLister | None = None,
        transcriber_factory: TranscriberFactory | None = None,
        compose_memory_context: MemoryContextComposer | None = None,
        resolve_channel: ChannelNoteResolver | None = None,
        resolve_home_env: HomeEnvResolver | None = None,
        is_managed: ManagedCheck | None = None,
        retrieve_memory: MemoryRetriever | None = None,
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
        # None ⇒ no memory append at all (feature not wired yet, or this
        # provider used outside the composition root that wires it) — never a
        # header with nothing under it.
        self._compose_memory_context = compose_memory_context
        # Turns the conversation's stored channel uid into the name the system
        # prompt reads. ``None`` ⇒ a channel turn still gets its channel append,
        # just without naming the channel — the uid is what decides that it IS a
        # channel turn, and the label was only ever colour.
        self._resolve_channel = resolve_channel
        # Points the spawned Claude Code at the agent's own config dir
        # (CLAUDE_CONFIG_DIR) when it is not ~/.claude, so a turn reads the
        # skills, MCP entry and settings Coffer put there. ``None`` ⇒ the
        # default dir, env untouched.
        self._resolve_home_env = resolve_home_env
        # Whether an enabled agent of this type is managed by Coffer; chat offers
        # and runs managed agents only. ``None`` ⇒ not asked.
        self._is_managed = is_managed
        # A channel turn's per-prompt notes (spec memory "Retrieve the notes a
        # prompt names for a channel turn"). ``None`` ⇒ none.
        self._retrieve_memory = retrieve_memory

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
        config = AgentConfig(
            cwd=str(resolved),
            model=model if isinstance(model, str) else None,
        )
        await self._conversations.set_agent_config(conversation_id, config)

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

        async def _save_session(session_id: str) -> None:
            latest = await self._conversations.get_agent_config(conversation_id)
            await self._conversations.set_agent_config(
                conversation_id, replace(latest, session_id=session_id)
            )

        system_context = await compose_system_context(
            agent_key=self.agent_key,
            channel_uid=conv.channel_uid or "",
            cwd=config.cwd,
            model=config.model,
            list_models=self._list_models,
            compose_memory=self._compose_memory_context,
            resolve_channel=self._resolve_channel,
            conversation_id=conversation_id,
        )

        # Overrides only: the SDK merges ``options.env`` over the daemon's own
        # environment itself. Empty for the default config dir.
        home_env = dict(await self._resolve_home_env()) if self._resolve_home_env else {}
        # A channel turn's process is marked, so the memory hook Claude Code runs
        # inside it leaves to this turn the index and notes it already carries
        # (spec memory "Deliver to channel turns through the system prompt").
        home_env.update(channel_turn_env(conv.channel_uid or ""))
        # The turn's token: the shim in the agent's MCP entry forwards it so
        # ``coffer__ask`` reaches this turn (spec mcp-gateway "Let an agent ask the
        # owner a question during a Coffer turn").
        home_env.update(questions.turn_env(conversation_id))

        return ClaudeSdkAgentAdapter(
            cwd=config.cwd,
            env=home_env or None,
            resume_session=config.session_id,
            extra={"model": config.model},
            session_factory=self._session_factory,
            on_session=_save_session,
            ask_owner=asker_for(conversation_id),
            system_context=system_context,
            # Claude cannot hear audio. A voice attachment is transcribed by the
            # user's configured connection, or handed over untouched when there
            # is none (spec channels "Transcribe inbound voice only when the
            # user opted in").
            transcriber=await self._transcriber(),
            # A document (PDF/office file) is text-extracted so it reaches the
            # agent as text rather than a vision/binary block (spec chat
            # "Extract document attachments to text").
            document_extractor=default_document_extractor(),
            prompt_memory=bind_prompt_memory(
                self._retrieve_memory,
                channel_uid=conv.channel_uid or "",
                agent_key=self.agent_key,
                cwd=config.cwd,
                conversation_id=conversation_id,
            ),
        )

    async def on_conversation_deleted(self, conversation_id: str) -> None:
        return

    async def _transcriber(self) -> Transcriber | None:
        if self._transcriber_factory is None:
            return None
        return await self._transcriber_factory()

    async def availability(self) -> bool:
        if self._which(self._binary) is None:
            return False
        return self._is_managed is None or await self._is_managed()


__all__ = ["ClaudeSdkProvider"]
