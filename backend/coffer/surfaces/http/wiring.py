"""Per-kind wiring helpers for the FastAPI composition root (specs 006/007).

Extracted from `app.py` so that file stays under the project's 400-LOC ceiling.
``build_substrate`` constructs the shared knowledge substrate ONCE per process
(unified ``DocumentRepo``, the ``SqliteKnowledgeIndex`` factory, the converter
registry, the cached ``make_embedder`` factory bound to the keychain, ripgrep,
the retrieval facade + reindexer); each `wire_<kind>` function takes it,
constructs the kind's service, registers the kind into ``app.state.kinds`` and
its built-in tools into the shared registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from coffer.application.builtin_tools import BuiltinToolRegistry
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
from coffer.domain.knowledge.embedder import EmbeddingConfig
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
from coffer.surfaces.http.dependencies import (
    set_kb_service,
    set_memory_service,
    set_project_root_repo,
)

if TYPE_CHECKING:
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from coffer.application.audit_service import AuditService
    from coffer.application.resource_service import ResourceService
    from coffer.domain.knowledge.converter import MarkdownConverter
    from coffer.domain.knowledge.index import KnowledgeIndex


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
) -> tuple[DocumentRepo, KnowledgeRetrieval, Reindexer]:
    """Construct the shared knowledge substrate over one session maker.

    The ``index_factory`` always attaches a ``VecIndex`` (maintenance mode when
    no width is given) so delete paths reach the vector rows; ``make_embedder``
    is bound to the keychain so cloud providers authenticate via stored creds.
    Call once per process and share across kinds.
    """
    documents = DocumentRepo(sm)
    keyring = KeyringAdapter()
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
            embedder = make_embedder(config, resolve_credential=keyring.get)
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
