"""The native-session source of each agent type, bound to its type.

``infrastructure/agent`` is where agent types may be named, so the pairing of
type and adapter lives here, each wrapped in the in-memory
:class:`SnapshotSessionSource` (stale-while-revalidate, never on disk). The
composition root only supplies the Codex transport (the chat package's
``default_app_server_session``, which this package may not import).
"""

from __future__ import annotations

from collections.abc import Mapping

from coffer.application.agent.native_session_service import NativeSessionSource
from coffer.application.agent.session_listing_snapshot import SnapshotSessionSource
from coffer.domain.agent.types import AgentType
from coffer.infrastructure.agent.claude_native_sessions import ClaudeNativeSessions
from coffer.infrastructure.agent.codex_native_sessions import CodexNativeSessions, SessionFactory


def native_session_sources(
    codex_session_factory: SessionFactory,
    *,
    fresh_s: float = 5.0,
) -> Mapping[AgentType, NativeSessionSource]:
    return {
        AgentType.CLAUDE_CODE: SnapshotSessionSource(ClaudeNativeSessions(), fresh_s=fresh_s),
        AgentType.CODEX: SnapshotSessionSource(
            CodexNativeSessions(codex_session_factory), fresh_s=fresh_s
        ),
    }


__all__ = ["native_session_sources"]
