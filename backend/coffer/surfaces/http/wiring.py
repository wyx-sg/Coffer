"""Chat wiring for the FastAPI composition root.

Extracted from `app.py` so that file stays under the project's 400-LOC ceiling.
The knowledge substrate this module used to build is gone with the index: the
knowledge kind now needs nothing but a directory, so it wires itself
(``knowledge_wiring.py``).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from coffer.application.agent.model_catalogue import AgentModelCatalogueService
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.application.providers.ports import ModelIntrospectionService
from coffer.domain.errors import CredentialMissing
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
from coffer.infrastructure.providers.provider_introspector import ProviderIntrospector
from coffer.surfaces.http.chat_provider_wiring import build_agent_provider_registry
from coffer.surfaces.http.dependencies import (
    get_agent_service,
    get_provider_service,
    set_agent_registry,
    set_chat_service,
    set_turn_orchestrator,
)
from coffer.surfaces.http.turn_dependencies import (
    set_agent_model_catalogue,
    set_introspection_service,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from coffer.application.mcp.gateway import MCPGatewaySession


_log = logging.getLogger(__name__)


def _sqlite_path(sm: async_sessionmaker[AsyncSession]) -> str | None:
    """The on-disk SQLite file path behind a session maker, or None for
    non-file backends (``:memory:``). ``VecIndex`` opens its own sync
    connection against this file because loadable extensions aren't exposed
    through aiosqlite."""
    bind = sm.kw.get("bind")
    database = getattr(getattr(bind, "url", None), "database", None)
    if not database or database == ":memory:":
        return None
    return str(database)


class _ActiveProviderModels:
    """``ActiveProviderModelsPort`` over the provider kind — the composition-root
    half of the catalogue's provider question.

    Resolves ``ProviderService`` lazily per call, so activating, re-targeting or
    curating a connection takes effect on the next card render with no rewiring.

    Matches the connection the same way the turn machinery does when it injects a
    key (``resolve_active_key_for_agent``): the first one flagged ``is_active``
    whose ``compatible_agents`` includes this agent type. An agent with no such
    connection runs on its own login, which is what ``None`` says.

    Narrowed to ``text``: the question is what a CHAT picker may offer, and the
    same endpoint's embedding, image, video and speech models would be rejected
    by every turn that tried them (spec provider-switching FR-030).
    """

    async def curated_models(self, agent_key: str) -> list[str] | None:
        try:
            resources = await get_provider_service().list()
        except Exception:
            # Nothing is wired yet, or the provider kind is unhappy: a catalogue
            # read degrades to "no active provider", never to an error.
            _log.debug("agent.catalogue.provider_lookup_failed", exc_info=True)
            return None
        for resource in resources:
            try:
                cfg = ProviderConfig.model_validate(resource.config)
            except ValueError:
                continue
            if cfg.is_active and agent_key in cfg.resolved_compatible_agents():
                return cfg.model_ids(Modality.TEXT)
        return None


def wire_chat(
    sm: object,
    mcp_session_factory: Callable[[str], Any],
    credential_store: Any,
) -> MCPGatewaySession:
    """Wire the agent-chat feature (spec channels) into the running app.

    Must be called **after** the ``BuiltinToolRegistry`` is fully populated
    (after knowledge, MCP, and skill wiring) so the ``coffer-builtin-agent``
    gateway session sees all built-in tools.

    Chat talks only to Coffer-managed agents (``claude_code`` / ``codex``); the
    former ``builtin`` chat persona is retired (ADR builtin-agent-is-internal-capability).

    Returns the long-lived ``MCPGatewaySession`` (the ``coffer-builtin-agent``
    session that backs Coffer's internal flows) so the caller (``_lifespan``)
    can dispose it on shutdown.
    """
    # 1. Persistence repos.
    conv_repo = ConversationRepo(sm)  # type: ignore[arg-type]
    msg_repo = MessageRepo(sm)  # type: ignore[arg-type]

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
    registry = build_agent_provider_registry(conv_repo, _credential_resolver)

    # 5. Application services + the agent-agnostic turn orchestrator.
    chat_svc = ChatService(
        conversations=conv_repo,
        messages=msg_repo,
        registry=registry,
    )
    orchestrator = TurnOrchestrator(chat_service=chat_svc, registry=registry)

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
    #      1. the Claude Code executable — its versioned catalog, which is the
    #         only place the Opus 5 / Opus 4.8 distinction is written down (its
    #         tier aliases are deliberately NOT offered: each one resolves to a
    #         model already in that catalog);
    #      2. Codex's own model/list RPC, driven over the same app-server
    #         transport a turn uses;
    #      3. each CLI's config file, for the local choices only it knows about.
    #    Needs the agent registry (spec agent-registry), which wire_agent_and_skill_kinds
    #    published before this call.
    model_catalogue = AgentModelCatalogueService(
        agents=get_agent_service(),
        discovery=ChainedModelDiscovery(
            [
                ClaudeBinaryModelDiscovery(),
                CodexRpcModelDiscovery(default_app_server_session),
                NativeConfigModelDiscovery(),
            ]
        ),
        provider_models=_ActiveProviderModels(),
    )

    # 9. Register dependency providers.
    set_chat_service(chat_svc)
    set_introspection_service(introspection_svc)
    set_turn_orchestrator(orchestrator)
    set_agent_registry(registry)
    set_agent_model_catalogue(model_catalogue)

    return agent_session
