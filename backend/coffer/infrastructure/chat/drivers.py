"""The driver facet implementations: Claude Code over the Agent SDK, Codex over
``codex app-server`` (ADR agent-mechanisms-are-optional-facets-on-the-descriptor).

Each driver declares the agent it serves by ``agent_key`` and builds its
``AgentProvider`` from :class:`DriverDeps`, the chat kind's dependencies. The
composition root binds the drivers to the agent descriptors and the chat
composition asks every bound driver to build, so neither place names an agent.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.infrastructure.chat.adapter_support import (
    ChannelNameResolver,
    HomeEnvResolver,
    MemoryContextComposer,
    ModelLister,
)
from coffer.infrastructure.chat.claude_sdk_provider import (
    ClaudeSdkProvider,
    TranscriberFactory,
)
from coffer.infrastructure.chat.codex_provider import CodexAppServerProvider

if TYPE_CHECKING:
    from coffer.application.chat.ports import AgentProvider
    from coffer.infrastructure.chat.persistence import ConversationRepo


@dataclass(frozen=True)
class DriverDeps:
    """What every driver may need. ``resolve_home_env`` and ``resolve_key`` are
    per-agent resolvers the composition builds from the agent's own key, so a
    driver never looks another agent up."""

    conversations: ConversationRepo
    list_models: ModelLister | None
    transcriber_factory: TranscriberFactory | None
    compose_memory_context: MemoryContextComposer | None
    resolve_channel_name: ChannelNameResolver | None
    resolve_home_env: Callable[[str], HomeEnvResolver]
    resolve_key: Callable[[str], Callable[[], Awaitable[str | None]]]


class ClaudeSdkDriver:
    """Claude Code, driven through the Claude Agent SDK."""

    agent_key = ClaudeSdkProvider.agent_key
    display_name = "Claude Code"

    def build(self, deps: DriverDeps) -> AgentProvider:
        # No key resolver: Claude Code reads its key through the projected
        # ``apiKeyHelper``, never from the spawn environment.
        return ClaudeSdkProvider(
            conversations=deps.conversations,
            list_models=deps.list_models,
            transcriber_factory=deps.transcriber_factory,
            compose_memory_context=deps.compose_memory_context,
            resolve_channel_name=deps.resolve_channel_name,
            resolve_home_env=deps.resolve_home_env(self.agent_key),
        )


class CodexAppServerDriver:
    """Codex, driven through ``codex app-server``."""

    agent_key = CodexAppServerProvider.agent_key
    display_name = "Codex"

    def build(self, deps: DriverDeps) -> AgentProvider:
        # Codex reads the projected key from ``COFFER_PROVIDER_KEY``, so the
        # key active for this agent is resolved per turn into its environment.
        return CodexAppServerProvider(
            conversations=deps.conversations,
            resolve_key=deps.resolve_key(self.agent_key),
            transcriber_factory=deps.transcriber_factory,
            list_models=deps.list_models,
            compose_memory_context=deps.compose_memory_context,
            resolve_channel_name=deps.resolve_channel_name,
            resolve_home_env=deps.resolve_home_env(self.agent_key),
        )


DRIVERS: tuple[ClaudeSdkDriver | CodexAppServerDriver, ...] = (
    ClaudeSdkDriver(),
    CodexAppServerDriver(),
)

__all__ = ["DRIVERS", "ClaudeSdkDriver", "CodexAppServerDriver", "DriverDeps"]
