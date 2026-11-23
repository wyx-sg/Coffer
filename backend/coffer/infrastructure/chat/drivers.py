"""The driver facet implementations: Claude Code over the Agent SDK, Codex over
``codex app-server``, and OpenCode, Cursor and DeepSeek Harness over their
one-shot commands (ADR agent-mechanisms-are-optional-facets-on-the-descriptor;
ADR cursor-opencode-and-deepseek-harness-chat-through-their-one-shot-commands).

Each driver declares the agent it serves by ``agent_key`` and builds its
``AgentProvider`` from :class:`DriverDeps`, the chat kind's dependencies. The
composition root binds the drivers to the agent descriptors and the chat
composition asks every bound driver to build, so neither place names an agent.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.infrastructure.chat.adapter_support import (
    ChannelNoteResolver,
    HomeEnvResolver,
    ManagedCheck,
    MemoryResolver,
    ModelLister,
)
from coffer.infrastructure.chat.claude_sdk_provider import (
    ClaudeSdkProvider,
    TranscriberFactory,
)
from coffer.infrastructure.chat.cli_provider import CliProvider
from coffer.infrastructure.chat.cli_turn import CliAgent
from coffer.infrastructure.chat.codex_provider import CodexAppServerProvider
from coffer.infrastructure.chat.cursor_print import CursorPrint
from coffer.infrastructure.chat.dsh_headless import DshHeadless
from coffer.infrastructure.chat.opencode_run import OpenCodeRun

if TYPE_CHECKING:
    from coffer.application.chat.ports import AgentProvider
    from coffer.infrastructure.chat.persistence import ConversationRepo


@dataclass(frozen=True)
class DriverDeps:
    """What every driver may need. ``resolve_home_env`` is a per-agent resolver
    the composition builds from the agent's own key, so a driver never looks
    another agent up."""

    conversations: ConversationRepo
    list_models: ModelLister | None
    transcriber_factory: TranscriberFactory | None
    resolve_channel: ChannelNoteResolver | None
    resolve_home_env: Callable[[str], HomeEnvResolver]
    #: Per-agent "is an enabled agent of this type managed" check (``None`` ⇒ not asked).
    is_managed: Callable[[str], ManagedCheck] | None = None
    #: The project memories a turn started in a directory is handed (``None`` ⇒ none).
    resolve_memory: MemoryResolver | None = None


class ClaudeSdkDriver:
    """Claude Code, driven through the Claude Agent SDK."""

    agent_key = ClaudeSdkProvider.agent_key
    display_name = "Claude Code"

    def build(self, deps: DriverDeps) -> AgentProvider:
        return ClaudeSdkProvider(
            conversations=deps.conversations,
            list_models=deps.list_models,
            transcriber_factory=deps.transcriber_factory,
            resolve_channel=deps.resolve_channel,
            resolve_home_env=deps.resolve_home_env(self.agent_key),
            is_managed=deps.is_managed(self.agent_key) if deps.is_managed else None,
            resolve_memory=deps.resolve_memory,
        )


class CodexAppServerDriver:
    """Codex, driven through ``codex app-server``."""

    agent_key = CodexAppServerProvider.agent_key
    display_name = "Codex"

    def build(self, deps: DriverDeps) -> AgentProvider:
        return CodexAppServerProvider(
            conversations=deps.conversations,
            transcriber_factory=deps.transcriber_factory,
            list_models=deps.list_models,
            resolve_channel=deps.resolve_channel,
            resolve_home_env=deps.resolve_home_env(self.agent_key),
            is_managed=deps.is_managed(self.agent_key) if deps.is_managed else None,
            resolve_memory=deps.resolve_memory,
        )


class CliDriver:
    """An agent driven through its one-shot command, one process per turn."""

    def __init__(self, agent: CliAgent, *, program: str, display_name: str) -> None:
        self._agent = agent
        self.agent_key = agent.agent_key
        self.program = program
        self.display_name = display_name

    def build(self, deps: DriverDeps) -> AgentProvider:
        return CliProvider(
            agent=self._agent,
            program=self.program,
            conversations=deps.conversations,
            list_models=deps.list_models,
            transcriber_factory=deps.transcriber_factory,
            resolve_channel=deps.resolve_channel,
            resolve_home_env=deps.resolve_home_env(self.agent_key),
            is_managed=deps.is_managed(self.agent_key) if deps.is_managed else None,
            resolve_memory=deps.resolve_memory,
        )


DRIVERS: tuple[ClaudeSdkDriver | CodexAppServerDriver | CliDriver, ...] = (
    ClaudeSdkDriver(),
    CodexAppServerDriver(),
    CliDriver(CursorPrint(), program="cursor-agent", display_name="Cursor"),
    CliDriver(OpenCodeRun(), program="opencode", display_name="OpenCode"),
    CliDriver(DshHeadless(), program="dsh", display_name="DeepSeek Harness"),
)

__all__ = ["DRIVERS", "ClaudeSdkDriver", "CliDriver", "CodexAppServerDriver", "DriverDeps"]
