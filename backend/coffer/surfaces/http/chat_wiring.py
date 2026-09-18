"""Chat wiring for the FastAPI composition root.

Builds the conversation/message repos, the registry of agent providers the
chat surface drives, the turn orchestrator, and the model-catalogue and
introspection services that tell the surface which models each agent offers.

Extracted from `app.py` so that file stays under the project's 400-LOC ceiling.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from coffer.application.agent.model_catalogue import AgentModelCatalogueService
from coffer.application.agent.service import AgentService
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.application.chat.turn_runner import DEFAULT_TURN_IDLE_TIMEOUT_SECONDS
from coffer.application.provider.introspection import ModelIntrospectionService
from coffer.application.provider.targets import projection_targets
from coffer.application.resource_service import ResourceService
from coffer.domain.errors import CredentialMissing, ResourceNotFound
from coffer.domain.provider.config import ProviderConfig
from coffer.domain.provider.modality import Modality
from coffer.infrastructure.agent.claude_binary_models import ClaudeBinaryModelDiscovery
from coffer.infrastructure.agent.codex_rpc_models import CodexRpcModelDiscovery
from coffer.infrastructure.agent.model_discovery import (
    ChainedModelDiscovery,
    NativeConfigModelDiscovery,
)
from coffer.infrastructure.chat.codex_app_server import default_app_server_session
from coffer.infrastructure.chat.persistence import ConversationRepo, MessageRepo
from coffer.infrastructure.credentials.encrypted_store import EncryptedCredentialStore
from coffer.infrastructure.provider.introspector import ProviderIntrospector
from coffer.surfaces.http.agent_dependencies import set_agent_model_catalogue
from coffer.surfaces.http.chat.dependencies import (
    set_agent_registry,
    set_chat_service,
    set_model_catalog,
    set_turn_orchestrator,
)
from coffer.surfaces.http.chat_provider_wiring import build_agent_provider_registry
from coffer.surfaces.http.mcp.dependencies import McpSessionFactory
from coffer.surfaces.http.provider_dependencies import (
    get_provider_service,
    set_introspection_service,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from coffer.application.mcp.gateway import MCPGatewaySession


_log = logging.getLogger(__name__)


def _turn_idle_timeout() -> float | None:
    """How long a turn may go without an event before the watchdog cancels it.

    ``COFFER_TURN_IDLE_TIMEOUT_SECONDS`` overrides the default (300); ``0`` or a
    value that does not parse as a positive number disables the watchdog.
    """
    raw = os.environ.get("COFFER_TURN_IDLE_TIMEOUT_SECONDS")
    if raw is None or not raw.strip():
        return DEFAULT_TURN_IDLE_TIMEOUT_SECONDS
    try:
        seconds = float(raw)
    except ValueError:
        _log.warning("COFFER_TURN_IDLE_TIMEOUT_SECONDS=%r is not a number; watchdog off", raw)
        return None
    return seconds if seconds > 0 else None


@dataclass(frozen=True)
class _ActiveProviderModels:
    """``ActiveProviderModelsPort`` over the provider kind — the composition-root
    half of the catalogue's provider question.

    Resolves ``ProviderService`` lazily per call (through the provider kind's
    getter — this runs at request time, by design), so activating, re-targeting
    or curating a connection takes effect on the next card render with no
    rewiring.

    Matches the connection the same way the turn machinery does when it injects a
    key (``resolve_active_key_for_agent``): the first one flagged ``is_active``
    whose per-agent SCOPE reaches this agent type (ADR per-agent-resource-scope) — and a
    disabled connection reaches none. An agent with no such connection runs on
    its own login, which is what ``None`` says.

    Narrowed to ``text``: the question is what a CHAT picker may offer, and the
    same endpoint's embedding, image, video and speech models would be rejected
    by every turn that tried them (spec provider-switching FR-032).
    """

    #: Held rather than resolved lazily like the provider service: a
    #: connection's reach names agent UIDS, so answering a question about an
    #: agent TYPE needs the agent registry, and that is a plain dependency.
    resources: ResourceService

    async def curated_models(self, agent_key: str) -> list[str] | None:
        try:
            connections = await get_provider_service().list()
            # A connection's reach is now an allow-list of agent UIDS, so
            # answering "does it cover this agent TYPE" means asking which
            # registered agents it reaches and what type each of those is. The
            # rows are fetched once, not per connection.
            agents = await self.resources.list(kind="agent")
        except Exception:
            # Nothing is wired yet, or the provider kind is unhappy: a catalogue
            # read degrades to "no active provider", never to an error.
            _log.debug("agent.catalogue.provider_lookup_failed", exc_info=True)
            return None
        for resource in connections:
            try:
                cfg = ProviderConfig.model_validate(resource.config)
            except ValueError:
                # A row this build cannot parse is not a candidate; the
                # provider kind's own validation reports it where it is edited.
                _log.debug("agent.catalogue.provider_config_invalid", extra={"name": resource.name})
                continue
            if cfg.is_active and any(
                t.value == agent_key for t in projection_targets(resource, cfg, agents)
            ):
                return cfg.model_ids(Modality.TEXT)
        return None


@dataclass(frozen=True)
class ChatWiring:
    """What the turn platform hands back to the lifespan.

    ``gateway_session`` is the long-lived ``coffer-builtin-agent`` session that
    backs Coffer's internal flows, disposed at shutdown; the rest is what the
    channel kind drives turns through, and the catalogue every model picker
    reads.
    """

    gateway_session: MCPGatewaySession
    chat_service: ChatService
    orchestrator: TurnOrchestrator
    registry: AgentProviderRegistry
    model_catalogue: AgentModelCatalogueService
    introspection_service: ModelIntrospectionService


def wire_chat(
    sm: async_sessionmaker[AsyncSession],
    mcp_session_factory: McpSessionFactory,
    credential_store: EncryptedCredentialStore,
    agent_service: AgentService,
    resource_service: ResourceService,
) -> ChatWiring:
    """Wire the agent-chat feature (spec channels) into the running app.

    Must be called **after** the ``BuiltinToolRegistry`` is fully populated
    (after knowledge, MCP, and skill wiring) so the ``coffer-builtin-agent``
    gateway session sees all built-in tools.

    Chat talks only to Coffer-managed agents (``claude_code`` / ``codex``); the
    former ``builtin`` chat persona is retired (ADR builtin-agent-is-internal-capability).
    """
    # 1. Persistence repos.
    conv_repo = ConversationRepo(sm)
    msg_repo = MessageRepo(sm)

    # 2. Long-lived in-process gateway session for the built-in agent. Built
    #    via the shared mcp_session_factory so it reuses the fully-populated
    #    BuiltinToolRegistry (knowledge + skill tools + MCP).
    agent_session: MCPGatewaySession = mcp_session_factory("coffer-builtin-agent")

    # 3. Credential resolver: resolve a credential ref → raw API key from the
    #    encrypted credential store.
    def _credential_resolver(ref: str) -> str:
        value: str | None = credential_store.get(ref)
        if value is None:
            # A domain error so a missing/revoked key surfaces as a mapped 400
            # (CREDENTIAL_MISSING) and the conversation stays usable, rather
            # than a generic 500 from a bare ValueError.
            raise CredentialMissing(ref)
        return value

    # 4. The agent-provider registry — the platform seam (chat_provider_wiring:
    #    adding an agent is one more register() call there).
    async def _channel_name(channel_uid: str) -> str | None:
        """The channel's current label, for the system-prompt line naming it.

        A conversation stores the channel's UID, so this is the read-time half
        of that split: the binding survives a rename and the model is told what
        the channel is called now. ``None`` for a channel that has since been
        deleted — the turn still came from a channel, it just has no name left.
        """
        try:
            return (await resource_service.get(channel_uid)).name
        except ResourceNotFound:
            return None

    registry = build_agent_provider_registry(
        conv_repo, _credential_resolver, resolve_channel_name=_channel_name
    )

    # 5. Application services + the agent-agnostic turn orchestrator.
    chat_svc = ChatService(
        conversations=conv_repo,
        messages=msg_repo,
        registry=registry,
    )
    orchestrator = TurnOrchestrator(
        chat_service=chat_svc, registry=registry, idle_timeout=_turn_idle_timeout()
    )

    # 6. Startup sweep: flip any lingering ``status='streaming'`` rows to
    #    ``'failed'`` (recover from a prior daemon crash).
    loop = asyncio.get_running_loop()

    async def _sweep() -> None:
        try:
            n = await TurnOrchestrator.sweep_streaming_messages(msg_repo)
            if n:
                _log.info("chat.startup_sweep: flipped %d streaming rows to failed", n)
        except Exception:
            _log.exception("chat.startup_sweep.failed")

    loop.create_task(_sweep())  # noqa: RUF006

    # 7. Provider introspection (test-connection + list-models). The OpenAI-
    #    compatible client + SSRF guard live in the infrastructure adapter; the
    #    service resolves credential refs to keys server-side.
    introspection_svc = ModelIntrospectionService(ProviderIntrospector(), _credential_resolver)

    # 8. The model catalogue — one list of models per managed agent, shared by
    #    the web picker, the channel /model card, and the note each turn tells
    #    the agent about the model it is on. Coffer names no model itself; it
    #    asks the two parties that know.
    #    First the ACTIVE provider for the agent type (``_ActiveProviderModels``
    #    below): when the user has pointed the agent at an endpoint of their own
    #    and ticked which of its models to use, those ids ARE the catalogue —
    #    the agent's built-in names are not served there.
    #    Otherwise the agent itself, from three sources whose ORDER here is the
    #    order the picker shows.
    #      1. the Claude Code executable — its tier aliases (``opus``,
    #         ``sonnet``, …), each labelled with the model it resolves to today,
    #         both read from the same embedded table. The versioned catalog it
    #         also carries is NOT offered: it is cumulative and account-blind,
    #         so it names models this account cannot run;
    #      2. Codex's own model/list RPC, driven over the same app-server
    #         transport a turn uses;
    #      3. each CLI's config file, for the local choices only it knows about.
    #    Needs the agent registry (spec agent-registry), handed in from
    #    wire_agent_and_skill_kinds' result.
    model_catalogue = AgentModelCatalogueService(
        agents=agent_service,
        discovery=ChainedModelDiscovery(
            [
                ClaudeBinaryModelDiscovery(),
                CodexRpcModelDiscovery(default_app_server_session),
                NativeConfigModelDiscovery(),
            ]
        ),
        provider_models=_ActiveProviderModels(resources=resource_service),
    )

    # 9. Register dependency providers. The catalogue is published twice on
    #    purpose: once as the agent kind's own service, once as the chat
    #    kind's ``ModelCatalogPort`` — the one seam that crosses a kind, so
    #    the chat surface never imports the agent kind.
    set_chat_service(chat_svc)
    set_introspection_service(introspection_svc)
    set_turn_orchestrator(orchestrator)
    set_agent_registry(registry)
    set_agent_model_catalogue(model_catalogue)
    set_model_catalog(model_catalogue)

    return ChatWiring(
        gateway_session=agent_session,
        chat_service=chat_svc,
        orchestrator=orchestrator,
        registry=registry,
        model_catalogue=model_catalogue,
        introspection_service=introspection_svc,
    )
