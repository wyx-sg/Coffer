"""Per-kind wiring helpers for the FastAPI composition root (specs 006/007).

Extracted from `app.py` so that file stays under the project's 400-LOC ceiling.
``build_substrate`` constructs the shared knowledge substrate ONCE per process
(unified ``DocumentRepo``, the ``SqliteKnowledgeIndex`` factory, the converter
registry, the cached ``make_embedder`` factory bound to the encrypted credential store, ripgrep,
the retrieval facade + reindexer); each `wire_<kind>` function takes it,
constructs the kind's service, registers the kind into ``app.state.kinds`` and
its built-in tools into the shared registry.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.chat.model_service import ModelService
from coffer.application.chat.registry import AgentProviderRegistry
from coffer.application.chat.service import ChatService
from coffer.application.chat.turn_orchestrator import TurnOrchestrator
from coffer.application.knowledge.reindex import Reindexer
from coffer.application.knowledge.retrieval import (
    EmbeddingResolver,
    KnowledgeRetrieval,
    no_embedding,
)
from coffer.application.knowledge_base.builtin_tools import register_kb_builtin_tools
from coffer.application.knowledge_base.kind import make_kb_kind
from coffer.application.knowledge_base.service import KnowledgeBaseService
from coffer.application.memory.builtin_tools import register_memory_builtin_tools
from coffer.application.memory.kind import make_memory_kind
from coffer.application.memory.scope import ScopeResolver
from coffer.application.memory.service import MemoryService
from coffer.application.memory.sync import MemoryReconciler
from coffer.application.providers.ports import ModelIntrospectionService
from coffer.domain.errors import CredentialMissing
from coffer.domain.knowledge.embedder import EmbeddingConfig
from coffer.infrastructure.chat.agentic_rag import DEFAULT_RECURSION_LIMIT, make_ask_tool
from coffer.infrastructure.chat.claude_sdk_provider import ClaudeSdkProvider
from coffer.infrastructure.chat.codex_provider import CodexAppServerProvider
from coffer.infrastructure.chat.gateway_tool_provider import GatewayToolProvider
from coffer.infrastructure.chat.model_persistence import ChatModelRepo
from coffer.infrastructure.chat.persistence import ConversationRepo, MessageRepo
from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.converters.registry import default_registry
from coffer.infrastructure.knowledge.embeddings import make_embedder
from coffer.infrastructure.knowledge.grep import RipgrepGrep
from coffer.infrastructure.knowledge.repository import DocumentRepo
from coffer.infrastructure.knowledge.sqlite_index import SqliteKnowledgeIndex
from coffer.infrastructure.knowledge.vec_index import VecIndex
from coffer.infrastructure.memory.project_root_repo import ProjectRootRepo
from coffer.infrastructure.memory.scope_fs import git_root, project_ulid
from coffer.infrastructure.providers.provider_introspector import ProviderIntrospector
from coffer.surfaces.http.chat.dependencies import set_introspection_service
from coffer.surfaces.http.dependencies import (
    set_agent_registry,
    set_chat_service,
    set_kb_service,
    set_memory_service,
    set_model_service,
    set_project_root_repo,
    set_turn_orchestrator,
)

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from coffer.application.audit_service import AuditService
    from coffer.application.mcp.gateway import MCPGatewaySession
    from coffer.application.resource_service import ResourceService
    from coffer.domain.knowledge.converter import MarkdownConverter
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


def wire_kb_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: object,
    builtin_tools: BuiltinToolRegistry,
    substrate: tuple[DocumentRepo, KnowledgeRetrieval, Reindexer] | None = None,
    embedding_resolver: EmbeddingResolver = no_embedding,
) -> KnowledgeBaseService:
    """Wire the ``knowledge_base`` kind (spec 006) into the app."""
    documents, retrieval, reindexer = substrate or build_substrate(sm)  # type: ignore[arg-type]
    kb_service = KnowledgeBaseService(
        resource_service=resource_svc,
        documents=documents,
        # ``ConverterRegistry`` provides the ``convert`` the service calls; it is
        # the production stand-in for the ``MarkdownConverter`` port.
        converters=cast("MarkdownConverter", default_registry()),
        retrieval=retrieval,
        reindexer=reindexer,
        audit=audit,
        paths=paths,
        embedding_resolver=embedding_resolver,
    )
    app.state.kinds["knowledge_base"] = make_kb_kind(kb_service)
    set_kb_service(kb_service)
    register_kb_builtin_tools(builtin_tools, resources=resource_svc, kb_service=kb_service)
    return kb_service


def wire_memory_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: object,
    builtin_tools: BuiltinToolRegistry,
    substrate: tuple[DocumentRepo, KnowledgeRetrieval, Reindexer] | None = None,
    embedding_resolver: EmbeddingResolver = no_embedding,
) -> MemoryService:
    """Wire the ``memory`` kind (spec 007) into the app."""
    documents, retrieval, reindexer = substrate or build_substrate(sm)  # type: ignore[arg-type]
    reconciler = MemoryReconciler(documents=documents, retrieval=retrieval, reindexer=reindexer)
    project_roots = ProjectRootRepo(sm)  # type: ignore[arg-type]
    set_project_root_repo(project_roots)
    scope = ScopeResolver(
        resources=resource_svc,
        git_root=git_root,
        project_ulid=project_ulid,
        store_dir=paths.memory_store_dir,
        record_project_root=project_roots.set,
    )
    memory_service = MemoryService(
        resource_service=resource_svc,
        documents=documents,
        scope_resolver=scope,
        reconciler=reconciler,
        retrieval=retrieval,
        audit=audit,
        store_dir=paths.memory_store_dir,
        fact_path=paths.fact_path,
        embedding_resolver=embedding_resolver,
    )
    app.state.kinds["memory"] = make_memory_kind(memory_service)
    set_memory_service(memory_service)
    register_memory_builtin_tools(builtin_tools, memory_service=memory_service)
    return memory_service


def _agent_recursion_limit() -> int:
    """Resolve the built-in agent's tool-iteration (graph recursion) limit.

    Configurable via ``COFFER_AGENT_RECURSION_LIMIT``; falls back to
    ``DEFAULT_RECURSION_LIMIT`` when unset, non-numeric, or non-positive.
    Each tool call is ~2 graph steps, so the limit bounds tool iterations.
    """
    raw = os.environ.get("COFFER_AGENT_RECURSION_LIMIT")
    if raw is None:
        return DEFAULT_RECURSION_LIMIT
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_RECURSION_LIMIT
    return value if value > 0 else DEFAULT_RECURSION_LIMIT


def wire_chat(
    audit: AuditService,
    sm: object,
    mcp_session_factory: Callable[[str], Any],
    credential_store: Any,
    builtin_tools: BuiltinToolRegistry,
) -> MCPGatewaySession:
    """Wire the agent-chat feature (spec 008) into the running app.

    Must be called **after** the ``BuiltinToolRegistry`` is fully populated
    (after KB, memory, MCP, and skill wiring) so the ``coffer-builtin-agent``
    gateway session sees all built-in tools.

    Chat talks only to Coffer-managed agents (``claude_code`` / ``codex``); the
    former ``builtin`` chat persona is retired (ADR-024). The local model lives
    on as an internal capability: this function registers the ``coffer__ask``
    agentic-retrieval built-in tool, which reuses the same gateway session.

    Returns the long-lived ``MCPGatewaySession`` (the ``coffer-builtin-agent``
    session that backs ``coffer__ask`` and other internal flows) so the caller
    (``_lifespan``) can dispose it on shutdown.
    """
    # 1. Persistence repos.
    conv_repo = ConversationRepo(sm)  # type: ignore[arg-type]
    msg_repo = MessageRepo(sm)  # type: ignore[arg-type]
    model_repo = ChatModelRepo(sm)  # type: ignore[arg-type]

    # 2. ModelService — the built-in agent's model registry.
    model_svc = ModelService(repo=model_repo, audit=audit)

    # 3. Long-lived in-process gateway session for the built-in agent. Built
    #    via the shared mcp_session_factory so it reuses the fully-populated
    #    BuiltinToolRegistry (KB + memory + skill tools + MCP).
    agent_session: MCPGatewaySession = mcp_session_factory("coffer-builtin-agent")
    tool_gateway = GatewayToolProvider(agent_session)

    # 4. Credential resolver: resolve a credential ref → raw API key from the
    #    encrypted credential store.
    def _credential_resolver(ref: str) -> str:
        value: str | None = credential_store.get(ref)
        if value is None:
            # A domain error so a missing/revoked key surfaces as a mapped 400
            # (CREDENTIAL_MISSING) and the conversation stays usable, rather
            # than a generic 500 from a bare ValueError.
            raise CredentialMissing(ref)
        return value

    # 5. ``coffer__ask`` — the local model's internal job (ADR-024). The retired
    #    builtin chat persona is replaced by an agentic-retrieval built-in tool
    #    that reuses the same gateway session + model registry. Registered into
    #    the (already-populated) BuiltinToolRegistry so every gateway session —
    #    including the one Claude Code / Codex connect to — advertises it. The
    #    tool exposes only read-only retrieval tools to its loop, so it can never
    #    recurse into itself.
    builtin_tools.register(
        make_ask_tool(
            model_service=model_svc,
            tool_gateway=tool_gateway,
            credential_resolver=_credential_resolver,
            recursion_limit=_agent_recursion_limit(),
        )
    )

    # 6. The agent-provider registry — the platform seam. Chat lists only
    #    Coffer-managed agents; a further agent is one more register() call here,
    #    with no change to the chat surface, persistence, or the wire contract.
    #    They surface in the picker only when their binary is on PATH (availability()).
    registry = AgentProviderRegistry()
    registry.register(ClaudeSdkProvider(conversations=conv_repo), display_name="Claude Code")
    registry.register(CodexAppServerProvider(conversations=conv_repo), display_name="Codex")

    # 7. Application services + the agent-agnostic turn orchestrator.
    chat_svc = ChatService(
        conversations=conv_repo,
        messages=msg_repo,
        registry=registry,
        audit=audit,
    )
    orchestrator = TurnOrchestrator(chat_service=chat_svc, registry=registry, audit=audit)

    # 8. Startup sweep: flip any lingering ``status='streaming'`` rows to
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

    # 8. Provider introspection (test-connection + list-models). The OpenAI-
    #    compatible client + SSRF guard live in the infrastructure adapter; the
    #    service resolves credential refs to keys server-side.
    introspection_svc = ModelIntrospectionService(ProviderIntrospector(), _credential_resolver)

    # 9. Register dependency providers.
    set_chat_service(chat_svc)
    set_model_service(model_svc)
    set_introspection_service(introspection_svc)
    set_turn_orchestrator(orchestrator)
    set_agent_registry(registry)

    return agent_session
