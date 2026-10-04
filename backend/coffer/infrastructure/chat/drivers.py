"""The driver facet implementations: Claude Code over the Agent SDK, Codex over
``codex app-server`` (ADR agent-mechanisms-are-optional-facets-on-the-descriptor).

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
    MemoryContextComposer,
    ModelLister,
)
from coffer.infrastructure.chat.claude_sdk_provider import (
    ClaudeSdkProvider,
    TranscriberFactory,
)
from coffer.infrastructure.chat.codex_provider import CodexAppServerProvider
from coffer.infrastructure.chat.prompt_memory import MemoryRetriever

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
    compose_memory_context: MemoryContextComposer | None
    resolve_channel: ChannelNoteResolver | None
    resolve_home_env: Callable[[str], HomeEnvResolver]
    #: Per-agent "is an enabled agent of this type managed" check (``None`` ⇒ not asked).
    is_managed: Callable[[str], ManagedCheck] | None = None
    #: A channel turn's per-prompt memory retrieval (``None`` ⇒ none).
    retrieve_memory: MemoryRetriever | None = None


class ClaudeSdkDriver:
    """Claude Code, driven through the Claude Agent SDK."""

    agent_key = ClaudeSdkProvider.agent_key
    display_name = "Claude Code"

    def build(self, deps: DriverDeps) -> AgentProvider:
        return ClaudeSdkProvider(
            conversations=deps.conversations,
            list_models=deps.list_models,
            transcriber_factory=deps.transcriber_factory,
            compose_memory_context=deps.compose_memory_context,
            retrieve_memory=deps.retrieve_memory,
            resolve_channel=deps.resolve_channel,
            resolve_home_env=deps.resolve_home_env(self.agent_key),
            is_managed=deps.is_managed(self.agent_key) if deps.is_managed else None,
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
            compose_memory_context=deps.compose_memory_context,
            retrieve_memory=deps.retrieve_memory,
            resolve_channel=deps.resolve_channel,
            resolve_home_env=deps.resolve_home_env(self.agent_key),
            is_managed=deps.is_managed(self.agent_key) if deps.is_managed else None,
        )


DRIVERS: tuple[ClaudeSdkDriver | CodexAppServerDriver, ...] = (
    ClaudeSdkDriver(),
    CodexAppServerDriver(),
)

__all__ = ["DRIVERS", "ClaudeSdkDriver", "CodexAppServerDriver", "DriverDeps"]
