"""Chat agent-provider registry wiring (spec channels), split from ``wiring.py``.

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
from coffer.application.engine.resolve import resolve_transcribe_connection
from coffer.domain.agent.types import AgentType
from coffer.domain.errors import CredentialMissing
from coffer.domain.provider.errors import NoActiveProvider
from coffer.infrastructure.chat.adapter_support import MemoryContextComposer
from coffer.infrastructure.chat.claude_sdk_provider import ClaudeSdkProvider
from coffer.infrastructure.chat.codex_provider import CodexAppServerProvider
from coffer.infrastructure.llm.transcription import remote_transcriber_factory
from coffer.surfaces.http.agent_dependencies import get_agent_model_catalogue
from coffer.surfaces.http.engine_config_composition import (
    read_internal_engine_timeout,
    read_transcribe_model,
)
from coffer.surfaces.http.provider_dependencies import get_provider_service

if TYPE_CHECKING:
    from coffer.infrastructure.chat.persistence import ConversationRepo


def build_agent_provider_registry(
    conv_repo: ConversationRepo,
    credential_resolver: Callable[[str], str] | None = None,
    compose_memory_context: MemoryContextComposer | None = None,
) -> AgentProviderRegistry:
    """Construct and populate the agent-provider registry.

    ``credential_resolver`` is what lets voice be transcribed: with it, a turn
    carrying audio reaches the connection the operator marked
    ``transcribe_default``, on the model they chose for it. Without the
    resolver, without such a connection, or without a model, audio is handed to
    the agent untouched and nothing leaves the machine. That is the default,
    and there is no fallback to the engine's own connection (spec
    internal-engine FR-025).

    ``compose_memory_context`` is the memory kind's own third system-prompt
    append (spec memory FR-024) for a channel-driven turn — a plain callable
    so this module, like ``claude_sdk_provider``, never imports anything from
    ``application.memory`` itself. Its real closure over
    ``MemoryService``/``OverrideRepository`` is built one level up, where
    those services are constructed; wire it in from there once they exist.
    ``None`` here (the default) means no memory append at all, not a header
    with nothing under it.
    """
    registry = AgentProviderRegistry()

    # Resolved per turn (lazily, through the provider kind's getter), so
    # designating or clearing the transcription connection takes effect
    # immediately. Returns None whenever transcription must not happen — which
    # is every turn until the operator marks a connection AND picks a model.
    transcriber_factory = (
        remote_transcriber_factory(
            lambda: resolve_transcribe_connection(
                read_model=read_transcribe_model, connections=get_provider_service()
            ),
            credential_resolver,
            read_internal_engine_timeout,
        )
        if credential_resolver is not None
        else None
    )

    # Tell Claude Code, on every turn, which model Coffer put it on and what
    # else it could be switched to — it cannot see either, and left to itself it
    # names a model at random. Resolved per turn (lazily, via the agent kind's
    # getter) because the catalogue service is built AFTER this registry in
    # ``wire_chat`` — it needs the registry-free agent service, and the
    # registry needs it — so the closure runs at request time by design.
    async def _list_models(agent_key: str) -> list[str]:
        ids: list[str] = await get_agent_model_catalogue().suggest(agent_key)
        return ids

    registry.register(
        ClaudeSdkProvider(
            conversations=conv_repo,
            list_models=_list_models,
            transcriber_factory=transcriber_factory,
            compose_memory_context=compose_memory_context,
        ),
        display_name="Claude Code",
    )

    # Codex reads Coffer's projected key from the COFFER_PROVIDER_KEY env var
    # (config.toml env_key). Resolve the connection active FOR that agent per turn —
    # keyed by agent, not wire, so an openai-compatible gateway routed to it
    # resolves correctly — and inject it into the subprocess env; with no active
    # connection it stays None so the agent uses its own login (the
    # provider-switching env_key seam). Lazy per turn by design: it runs at
    # request time, so the provider kind's getter is the right seam.
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
        CodexAppServerProvider(
            conversations=conv_repo,
            resolve_key=_key_resolver(AgentType.CODEX),
            transcriber_factory=transcriber_factory,
            list_models=_list_models,
            compose_memory_context=compose_memory_context,
        ),
        display_name="Codex",
    )
    return registry
