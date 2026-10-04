"""The native-session source of each agent type, bound to its type.

``infrastructure/agent`` is where agent types may be named, so the pairing of
type and adapter lives here and the composition root only supplies the Codex
transport (the chat package's ``default_app_server_session``, which this
package may not import).
"""

from __future__ import annotations

from collections.abc import Mapping

from coffer.application.agent.native_session_service import NativeSessionSource
from coffer.domain.agent.types import AgentType
from coffer.infrastructure.agent.claude_native_sessions import ClaudeNativeSessions
from coffer.infrastructure.agent.codex_native_sessions import CodexNativeSessions, SessionFactory


def native_session_sources(
    codex_session_factory: SessionFactory,
) -> Mapping[AgentType, NativeSessionSource]:
    return {
        AgentType.CLAUDE_CODE: ClaudeNativeSessions(),
        AgentType.CODEX: CodexNativeSessions(codex_session_factory),
    }


__all__ = ["native_session_sources"]
