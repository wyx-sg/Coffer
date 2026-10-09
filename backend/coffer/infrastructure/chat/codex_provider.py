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
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any

from coffer.application.chat import questions
from coffer.application.chat.ports import AgentAdapter
from coffer.application.chat.service import ConversationRepo
from coffer.domain.chat.agent_config import AgentConfig
from coffer.domain.chat.errors import AgentConfigRejected, ConversationNotFound
from coffer.infrastructure.chat.adapter_support import (
    ChannelNoteResolver,
    HomeEnvResolver,
    ManagedCheck,
    ModelLister,
    compose_system_context,
    require_managed,
)
from coffer.infrastructure.chat.codex_agent import CodexAppServerAdapter
from coffer.infrastructure.chat.codex_app_server import (
    AppServerSessionFactory,
    default_app_server_session,
)
from coffer.infrastructure.chat.default_workspace import default_workspace_dir
from coffer.infrastructure.chat.document_extract import default_document_extractor
from coffer.infrastructure.chat.transcribe import Transcriber
from coffer.infrastructure.platform.user_path import which_on_user_path

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
        which: Any = which_on_user_path,
        transcriber_factory: TranscriberFactory | None = None,
        list_models: ModelLister | None = None,
        resolve_channel: ChannelNoteResolver | None = None,
        resolve_home_env: HomeEnvResolver | None = None,
        is_managed: ManagedCheck | None = None,
    ) -> None:
        self._conversations = conversations
        self._session_factory: AppServerSessionFactory = (
            session_factory or default_app_server_session
        )
        self._which = which
        # None ⇒ voice is never transcribed and the audio file reaches the agent
        # as-is. That is the default: nothing leaves the machine unasked.
        self._transcriber_factory = transcriber_factory
        # The same two notes the SDK provider has always sent. Codex sent
        # neither of them until the app-server's
        # ``developerInstructions`` field made it possible — so a Codex agent
        # answering a phone had no idea it was on one.
        self._list_models = list_models
        # Turns the conversation's stored channel uid into the name the system
        # prompt reads. ``None`` ⇒ a channel turn still gets its channel append,
        # just without naming the channel — the uid is what decides that it IS a
        # channel turn, and the label was only ever colour.
        self._resolve_channel = resolve_channel
        # Points the spawned app-server at the agent's own config dir
        # (CODEX_HOME) when it is not ~/.codex. ``None`` ⇒ the default dir.
        self._resolve_home_env = resolve_home_env
        # Whether an enabled agent of this type is managed by Coffer; chat offers
        # and runs managed agents only. ``None`` ⇒ not asked.
        self._is_managed = is_managed

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

        # No provider key rides the environment: an API-key connection is
        # reached through Coffer's model proxy, which injects the real key
        # upstream, and Codex authenticates to the proxy with its own ``auth``
        # command. The overrides are CODEX_HOME, when the agent has its own
        # config dir, and the turn's token — MERGED with os.environ,
        # because create_subprocess_exec REPLACES the environment; with none
        # the env stays None (inherit).
        overrides: dict[str, str] = (
            dict(await self._resolve_home_env()) if self._resolve_home_env else {}
        )
        # The turn's token, for ``coffer__ask`` (the ``coffer`` entry in Codex's
        # config passes ``COFFER_TURN_TOKEN`` through to the shim).
        overrides.update(questions.turn_env(conversation_id))
        env = {**os.environ, **overrides} if overrides else None
        system_context = await compose_system_context(
            agent_key=self.agent_key,
            channel_uid=conv.channel_uid or "",
            model=config.model,
            list_models=self._list_models,
            resolve_channel=self._resolve_channel,
            conversation_id=conversation_id,
        )

        return CodexAppServerAdapter(
            cwd=config.cwd,
            system_context=system_context,
            resume_session=config.session_id,
            extra={"model": config.model},
            session_factory=self._session_factory,
            on_session=_save_session,
            env=env,
            # Codex cannot hear audio. A voice attachment is transcribed by the
            # user's configured connection, or handed over untouched when there
            # is none (spec channels "Transcribe inbound voice only when the
            # user opted in").
            transcriber=await self._transcriber(),
            # Codex is path-native and cannot parse a binary PDF; a document is
            # text-extracted so it reaches the agent as text (spec chat "Extract
            # document attachments to text").
            document_extractor=default_document_extractor(),
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


__all__ = ["CodexAppServerProvider"]
