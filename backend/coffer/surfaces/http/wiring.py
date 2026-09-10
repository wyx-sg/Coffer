"""Shared-substrate + chat wiring for the FastAPI composition root.

Extracted from `app.py` so that file stays under the project's 400-LOC ceiling.
``build_substrate`` constructs the shared knowledge substrate ONCE per process
(unified ``DocumentRepo``, the ``SqliteKnowledgeIndex`` factory, the cached
``make_embedder`` factory bound to the encrypted credential store, ripgrep, the
retrieval facade + reindexer); the knowledge kind's own wiring
(``knowledge_wiring.py``) takes it and builds the one service over it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from coffer.application.agent.model_catalogue import AgentModelCatalogueService
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.application.knowledge.reindex import Reindexer
from coffer.application.knowledge.retrieval import (
    KnowledgeRetrieval,
)
from coffer.application.providers.ports import ModelIntrospectionService
from coffer.domain.errors import CredentialMissing
from coffer.domain.knowledge.embedder import EmbeddingConfig
from coffer.infrastructure.agent.claude_binary_models import ClaudeBinaryModelDiscovery
from coffer.infrastructure.agent.codex_rpc_models import CodexRpcModelDiscovery
from coffer.infrastructure.agent.model_discovery import (
    ChainedModelDiscovery,
    NativeConfigModelDiscovery,
)
from coffer.infrastructure.chat.codex_app_server import default_app_server_session
from coffer.infrastructure.chat.persistence import ConversationRepo, MessageRepo
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.infrastructure.knowledge.embeddings import make_embedder
from coffer.infrastructure.knowledge.grep import RipgrepGrep
from coffer.infrastructure.knowledge.repository import DocumentRepo
from coffer.infrastructure.knowledge.sqlite_index import SqliteKnowledgeIndex
from coffer.infrastructure.knowledge.vec_index import VecIndex
from coffer.infrastructure.providers.provider_introspector import ProviderIntrospector
from coffer.surfaces.http.chat_provider_wiring import build_agent_provider_registry
from coffer.surfaces.http.dependencies import (
    get_agent_service,
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
    from coffer.domain.knowledge.index import KnowledgeIndex


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


def build_substrate(
    sm: async_sessionmaker[AsyncSession],
    credential_store: Any | None = None,
) -> tuple[DocumentRepo, KnowledgeRetrieval, Reindexer]:
    """Construct the shared knowledge substrate over one session maker.

    The ``index_factory`` always attaches a ``VecIndex`` (maintenance mode when
    no width is given) so delete paths reach the vector rows; ``make_embedder``
    is bound to the encrypted credential store so cloud providers authenticate
    via stored creds. Call once per process and share across kinds.

    ``credential_store`` is the EncryptedCredentialStore in production; tests
    that exercise no cloud embedder may omit it (falls back to the OS keychain
    adapter, which resolves nothing unless seeded).
    """
    documents = DocumentRepo(sm)
    creds = credential_store if credential_store is not None else KeyringAdapter()
    db_path = _sqlite_path(sm)

    def index_factory(kind: str, resource_name: str, *, dimensions: int | None) -> KnowledgeIndex:
        # Per-store vector table (named by kind+resource_name): isolates stores
        # so differing widths coexist and a scoped KNN never leaks across
        # stores. The vec index is ALWAYS attached (maintenance mode when no
        # width is given) so delete paths — which know no embedding width —
        # still reach the store's vector rows.
        vec: VecIndex | None = None
        if db_path is not None:
            vec = VecIndex(db_path, dimensions, kind=kind, resource_name=resource_name)
        return SqliteKnowledgeIndex(sm, kind=kind, resource_name=resource_name, vec=vec)

    # One embedder per config: rebuilding per call leaked an AsyncOpenAI
    # (httpx pool) every vector query/write. Keyed by the config's fields
    # (pydantic models are not hashable).
    embedder_cache: dict[tuple[object, ...], object] = {}

    def embedder_factory(config: EmbeddingConfig) -> object:
        key = (
            config.provider,
            config.model,
            config.base_url,
            config.credential_ref,
            config.dimensions,
        )
        embedder = embedder_cache.get(key)
        if embedder is None:
            embedder = make_embedder(config, resolve_credential=creds.get)
            embedder_cache[key] = embedder
        return embedder

    retrieval = KnowledgeRetrieval(
        index_factory=index_factory,
        grep=RipgrepGrep(),
        embedder_factory=embedder_factory,  # type: ignore[arg-type]
    )
    reindexer = Reindexer(embedder_factory=embedder_factory)  # type: ignore[arg-type]
    return documents, retrieval, reindexer


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
    #    the agent about the model it is on. Coffer names no model itself: every
    #    entry is read back from the agent, from three sources whose ORDER here
    #    is the order the picker shows.
    #      1. the Claude Code executable — its tier aliases, then its versioned
    #         catalog, which is the only place the Opus 5 / Opus 4.8 distinction
    #         is written down;
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
    )

    # 9. Register dependency providers.
    set_chat_service(chat_svc)
    set_introspection_service(introspection_svc)
    set_turn_orchestrator(orchestrator)
    set_agent_registry(registry)
    set_agent_model_catalogue(model_catalogue)

    return agent_session
