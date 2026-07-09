"""Chat agent-provider registry wiring (spec 008), split from ``wiring.py``.

The agent-provider registry is the platform seam: chat lists only
Coffer-managed agents, and a further agent is one more ``register()`` call
here, with no change to the chat surface, persistence, or the wire contract.
Providers surface in the picker only when their binary is on PATH
(``availability()``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from coffer.application.chat.registry import AgentProviderRegistry
from coffer.domain.agent.types import AgentType
from coffer.domain.errors import CredentialMissing
from coffer.domain.provider.errors import NoActiveProvider
from coffer.infrastructure.chat.claude_sdk_provider import ClaudeSdkProvider
from coffer.infrastructure.chat.codex_provider import CodexAppServerProvider
from coffer.infrastructure.chat.cursor_provider import CursorProvider
from coffer.infrastructure.chat.hermes_provider import HermesProvider
from coffer.infrastructure.chat.opencode_provider import OpencodeProvider
from coffer.surfaces.http.dependencies import get_provider_service

if TYPE_CHECKING:
    from coffer.infrastructure.chat.persistence import ConversationRepo


def build_agent_provider_registry(conv_repo: ConversationRepo) -> AgentProviderRegistry:
    """Construct and populate the chat agent-provider registry."""
    registry = AgentProviderRegistry()
    registry.register(ClaudeSdkProvider(conversations=conv_repo), display_name="Claude Code")

    # Codex / opencode / hermes each read Coffer's projected key from the
    # COFFER_PROVIDER_KEY env var (config.toml env_key; opencode.json + config.yaml
    # {env:...} references). Resolve the connection active FOR that agent per turn —
    # keyed by agent, not wire, so an openai-compatible gateway routed to any of them
    # resolves correctly — and inject it into the subprocess env; with no active
    # connection it stays None so the agent uses its own login (ADR-032 env_key seam).
    def _key_resolver(agent_type: AgentType) -> Callable[[], Awaitable[str | None]]:
        async def _resolve() -> str | None:
            try:
                # Assign to a typed local so mypy narrows the service's Any return.
                key: str = await get_provider_service().resolve_active_key_for_agent(agent_type)
                return key
            except (NoActiveProvider, CredentialMissing):
                return None

        return _resolve

    registry.register(
        CodexAppServerProvider(conversations=conv_repo, resolve_key=_key_resolver(AgentType.CODEX)),
        display_name="Codex",
    )
    registry.register(
        OpencodeProvider(conversations=conv_repo, resolve_key=_key_resolver(AgentType.OPENCODE)),
        display_name="opencode",
    )

    # hermes has no working upstream hook, so its session context lives in a
    # static SOUL.md block (ADR-042 INSTRUCTIONS_BLOCK) that this closure
    # re-renders before each Coffer-driven turn. Lazy getter: the hook service
    # is wired by agent_skill_wiring, after this module.
    async def _refresh_hermes_blocks() -> int:
        from coffer.surfaces.http.dependencies import get_agent_hook_service

        count: int = await get_agent_hook_service().refresh_blocks_for_type(AgentType.HERMES)
        return count

    registry.register(
        HermesProvider(
            conversations=conv_repo,
            resolve_key=_key_resolver(AgentType.HERMES),
            refresh_context=_refresh_hermes_blocks,
        ),
        display_name="Hermes",
    )
    # Cursor is locked to Cursor's own backend and uses its OWN auth
    # (`cursor-agent login` / CURSOR_API_KEY): Coffer projects no connection and
    # injects no key, so there is NO resolve_key here (provider-projection-N/A).
    registry.register(CursorProvider(conversations=conv_repo), display_name="Cursor")
    return registry
