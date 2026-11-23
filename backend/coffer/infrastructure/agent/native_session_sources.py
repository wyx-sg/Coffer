"""The native-session source of each agent type, bound to its type.

``infrastructure/agent`` is where agent types may be named, so the pairing of
type and adapter lives here, each wrapped in the in-memory
:class:`SnapshotSessionSource` (stale-while-revalidate, never on disk). The
composition root supplies the Codex transport (the chat package's
``default_app_server_session``, which this package may not import) and, for
the agents whose stores Coffer reads directly, the source to fall back on when
a store cannot be read (the conversations Coffer ran on the agent).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from coffer.application.agent.native_session_service import NativeSessionSource
from coffer.application.agent.session_listing_fallback import FallbackSessionSource
from coffer.application.agent.session_listing_snapshot import SnapshotSessionSource
from coffer.domain.agent.types import AgentType
from coffer.infrastructure.agent.claude_native_sessions import ClaudeNativeSessions
from coffer.infrastructure.agent.cli_native_sessions import (
    CursorNativeSessions,
    DshNativeSessions,
    OpenCodeNativeSessions,
    StoreUnreadable,
)
from coffer.infrastructure.agent.codex_native_sessions import CodexNativeSessions, SessionFactory
from coffer.infrastructure.platform.user_path import user_path_env, which_on_user_path


def native_session_sources(
    codex_session_factory: SessionFactory,
    *,
    fallback: Callable[[AgentType], NativeSessionSource] | None = None,
    fresh_s: float = 5.0,
) -> Mapping[AgentType, NativeSessionSource]:
    sources: dict[AgentType, NativeSessionSource] = {
        AgentType.CLAUDE_CODE: SnapshotSessionSource(ClaudeNativeSessions(), fresh_s=fresh_s),
        AgentType.CODEX: SnapshotSessionSource(
            CodexNativeSessions(codex_session_factory), fresh_s=fresh_s
        ),
    }
    store_readers: dict[AgentType, NativeSessionSource] = {
        AgentType.OPENCODE: OpenCodeNativeSessions(which=which_on_user_path, env=user_path_env),
        AgentType.DEEPSEEK_HARNESS: DshNativeSessions(),
        AgentType.CURSOR: CursorNativeSessions(),
    }
    for agent_type, reader in store_readers.items():
        snapshot = SnapshotSessionSource(reader, fresh_s=fresh_s)
        sources[agent_type] = (
            FallbackSessionSource(snapshot, fallback(agent_type), unreadable=(StoreUnreadable,))
            if fallback is not None
            else snapshot
        )
    return sources


__all__ = ["native_session_sources"]
