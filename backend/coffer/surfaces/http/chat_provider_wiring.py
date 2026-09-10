"""Chat agent-provider registry wiring (spec 008), split from ``wiring.py``.

The agent-provider registry is the platform seam: chat lists only Coffer's two
managed agents — Claude Code and Codex — and a further agent would be one more
``register()`` call here, with no change to the chat surface, persistence, or
the wire contract. Providers surface in the picker only when their binary is on
PATH (``availability()``).
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
from coffer.surfaces.http.dependencies import get_provider_service
from coffer.surfaces.http.turn_dependencies import get_agent_model_catalogue

if TYPE_CHECKING:
    from coffer.infrastructure.chat.persistence import ConversationRepo


def build_agent_provider_registry(conv_repo: ConversationRepo) -> AgentProviderRegistry:
    """Construct and populate the chat agent-provider registry."""
    registry = AgentProviderRegistry()

    # Tell Claude Code, on every turn, which model Coffer put it on and what
    # else it could be switched to — it cannot see either, and left to itself it
    # names a model at random. Resolved per turn (lazily, via the DI getter)
    # because the catalogue service is published later in the same lifespan.
    async def _list_models(agent_key: str) -> list[str]:
        ids: list[str] = await get_agent_model_catalogue().suggest(agent_key)
        return ids

    registry.register(
        ClaudeSdkProvider(conversations=conv_repo, list_models=_list_models),
        display_name="Claude Code",
    )

    # Codex reads Coffer's projected key from the COFFER_PROVIDER_KEY env var
    # (config.toml env_key). Resolve the connection active FOR that agent per turn —
    # keyed by agent, not wire, so an openai-compatible gateway routed to it
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
    return registry
