"""Chat agent-provider registry wiring (spec chat), split from ``wiring.py``.

The agent-provider registry is the platform seam: chat lists the agents whose
descriptor carries a driver facet (ADR
agent-mechanisms-are-optional-facets-on-the-descriptor) — Claude Code over the
Agent SDK, Codex over ``codex app-server`` — and a further agent is one more
driver bound at the composition root, with no change here, to the chat
surface, persistence, or the wire contract. Providers surface in the picker
only when their binary is on PATH and an enabled managed agent of that type is
registered (``availability()``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from coffer.application.agent.answering import AgentLister, answering_agent_config
from coffer.application.chat.ports import QuotaObserver
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.engine.resolve import resolve_transcribe_connection
from coffer.domain.agent.facets import AgentCatalog
from coffer.infrastructure.chat.adapter_support import (
    ChannelNoteResolver,
    MemoryContextComposer,
)
from coffer.infrastructure.chat.drivers import DriverDeps
from coffer.infrastructure.chat.prompt_memory import MemoryRetriever
from coffer.infrastructure.llm.transcription import remote_transcriber_factory
from coffer.surfaces.http.agent_dependencies import (
    get_agent_model_catalogue,
    get_agent_service,
)
from coffer.surfaces.http.engine_config_composition import (
    read_internal_engine_timeout,
    read_transcribe_model,
)
from coffer.surfaces.http.provider_dependencies import get_provider_service

if TYPE_CHECKING:
    from coffer.infrastructure.chat.persistence import ConversationRepo


def agent_home_env_resolver(
    agent_key: str, agents: Callable[[], AgentLister] = get_agent_service
) -> Callable[[], Awaitable[dict[str, str]]]:
    """The environment a turn on the agent type ``agent_key`` runs under,
    resolved per turn.

    The agent answering for the type (``answering_agent_config`` — the same one
    the model catalogue reads) decides it: a custom ``config_dir`` becomes
    ``CLAUDE_CONFIG_DIR`` / ``CODEX_HOME``, the default one (or no registered
    agent) sets nothing (spec chat "Ship Claude Code and Codex subprocess
    providers on the type's one agent"). ``agents`` is a getter so the registry is read at request
    time, after the composition root has published it, and so a changed
    ``config_dir`` takes effect on the next turn without a restart.
    """

    async def _resolve() -> dict[str, str]:
        cfg = await answering_agent_config(agents(), agent_key)
        return {} if cfg is None else cfg.runtime_env()

    return _resolve


def agent_is_managed(
    agent_key: str, agents: Callable[[], AgentLister] = get_agent_service
) -> Callable[[], Awaitable[bool]]:
    """Whether an ENABLED agent of the type ``agent_key`` is registered with Coffer,
    read per call (spec chat "Offer and run only managed agents"): chat offers a type
    only once one is, and a turn for a type without one is refused, so a conversation
    never runs against an agent's default config dir that Coffer was told to leave alone."""

    async def _managed() -> bool:
        return await answering_agent_config(agents(), agent_key) is not None

    return _managed


def build_agent_provider_registry(
    conv_repo: ConversationRepo,
    agent_catalog: AgentCatalog,
    secret_resolver: Callable[[str], str] | None = None,
    compose_memory_context: MemoryContextComposer | None = None,
    resolve_channel: ChannelNoteResolver | None = None,
    observe_quota: QuotaObserver | None = None,
    retrieve_memory: MemoryRetriever | None = None,
) -> AgentProviderRegistry:
    """Construct and populate the agent-provider registry.

    ``secret_resolver`` is what lets voice be transcribed: with it, a turn
    carrying audio reaches the connection the operator marked
    ``transcribe_default``, on the model they chose for it. Without the
    resolver, without such a connection, or without a model, audio is handed to
    the agent untouched and nothing leaves the machine. That is the default,
    and there is no fallback to the engine's own connection (spec
    internal-engine "Transcribe speech on its own connection and model").

    ``resolve_channel`` turns the channel UID a conversation stores into the
    facts the channel note is written from — the channel's current name, its
    platform, whether the conversation is a direct chat or a group thread, and
    what renders there. The row holds the identity so a renamed channel keeps
    its conversations; the facts are resolved here, at read time, so the model
    is told what the channel is called NOW rather than when the thread started.
    ``None`` means the append still happens — the turn really did arrive over a
    channel — without naming it.

    ``compose_memory_context`` is the memory kind's own system-prompt append
    (spec memory "Deliver to channel turns through the system prompt") for a
    channel-driven turn — a plain callable so this module, like
    ``claude_sdk_provider``, never imports anything from ``application.memory``
    itself. The composition root builds the real closure over ``MemoryService``
    (``memory_turn_wiring.memory_context_composer``) and hands it through
    ``wire_chat``. ``None`` means no memory append at all, not a header with
    nothing under it.

    ``observe_quota`` receives each driven agent's official subscription-quota
    report — Claude Code's ``rate_limit_event``, Codex's
    ``account/rateLimits/updated`` (ADR usage-is-metered-at-the-proxy-and-
    subscriptions-show-only-official-quota); the composition root binds the
    usage kind's quota service. ``None`` means the reports are dropped.

    ``retrieve_memory`` ranks a channel turn's prompt against the notes (spec
    memory "Retrieve the notes a prompt names for a channel turn"); the
    composition root builds it (``memory_turn_wiring``). ``None`` means none.
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
            secret_resolver,
            read_internal_engine_timeout,
        )
        if secret_resolver is not None
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

    deps = DriverDeps(
        conversations=conv_repo,
        list_models=_list_models,
        transcriber_factory=transcriber_factory,
        compose_memory_context=compose_memory_context,
        resolve_channel=resolve_channel,
        resolve_home_env=agent_home_env_resolver,
        is_managed=agent_is_managed,
        observe_quota=observe_quota,
        retrieve_memory=retrieve_memory,
    )
    # Every agent with a driver facet, in agent-type order.
    for driver in agent_catalog.drivers():
        registry.register(driver.build(deps), display_name=driver.display_name)
    return registry
