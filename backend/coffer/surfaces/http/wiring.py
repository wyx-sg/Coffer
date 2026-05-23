"""Per-kind wiring helpers for the FastAPI composition root.

Extracted from `app.py` so that file stays under the project's 400-LOC
ceiling. Each `_wire_<kind>` function takes the kind-agnostic services
plus the shared `BuiltinToolRegistry`, builds the kind-specific store +
service + Kind, and registers everything into the running app.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.knowledge_base.builtin_tools import register_kb_builtin_tools
from coffer.application.knowledge_base.kind import make_kb_kind
from coffer.application.knowledge_base.service import KnowledgeBaseService
from coffer.application.memory.builtin_tools import register_memory_builtin_tools
from coffer.application.memory.kind import make_memory_kind
from coffer.application.memory.service import MemoryService
from coffer.infrastructure.knowledge_base.llamaindex_store import (
    LlamaIndexKnowledgeBaseStore,
)
from coffer.infrastructure.knowledge_base.loaders import extract_text
from coffer.infrastructure.knowledge_base.paths import (
    kb_dir,
    kb_raw_dir,
    kb_root,
    raw_file_path,
)
from coffer.infrastructure.knowledge_base.persistence import (
    SqlAlchemyKBDocumentRepo,
)
from coffer.infrastructure.memory.mem0_store import Mem0MemoryStore
from coffer.infrastructure.memory.paths import memory_store_dir
from coffer.infrastructure.memory.persistence import SqlAlchemyMemoryRecordRepo
from coffer.infrastructure.observability import make_tracer
from coffer.surfaces.http.dependencies import set_kb_service, set_memory_service

if TYPE_CHECKING:
    from fastapi import FastAPI

    from coffer.application.audit_service import AuditService
    from coffer.application.resource_service import ResourceService


def wire_kb_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: object,
    builtin_tools: BuiltinToolRegistry,
) -> LlamaIndexKnowledgeBaseStore:
    """Wire KB plumbing into the app."""
    store = LlamaIndexKnowledgeBaseStore()
    doc_repo = SqlAlchemyKBDocumentRepo(sm)  # type: ignore[arg-type]
    tracer = make_tracer()
    kb_service = KnowledgeBaseService.build(
        resource_service=resource_svc,
        store=store,
        documents=doc_repo,
        audit=audit,
        tracer=tracer,
        raw_dir=kb_raw_dir,
        raw_file=raw_file_path,
        kb_dir=kb_dir,
        kb_root=kb_root,
        extractor=extract_text,
    )
    app.state.kinds["knowledge_base"] = make_kb_kind(kb_service)
    set_kb_service(kb_service)
    register_kb_builtin_tools(builtin_tools, resources=resource_svc, kb_service=kb_service)
    return store


def wire_memory_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    sm: object,
    builtin_tools: BuiltinToolRegistry,
) -> Mem0MemoryStore:
    """Wire Memory plumbing into the app."""
    # CODE26-002: thread the keyring resolver into the mem0 adapter so the
    # openai LLM provider can authenticate using the user's stored API key
    # (referenced by ``MemoryStoreConfig.llm_credential_ref``). Imported
    # locally to avoid widening the wiring module's top-level imports.
    from coffer.infrastructure.credentials.keyring_adapter import KeyringAdapter

    _kr = KeyringAdapter()
    store = Mem0MemoryStore(credential_resolver=_kr.get)
    record_repo = SqlAlchemyMemoryRecordRepo(sm)  # type: ignore[arg-type]
    tracer = make_tracer()
    memory_service = MemoryService(
        resource_service=resource_svc,
        store=store,
        records=record_repo,
        audit=audit,
        tracer=tracer,
        store_dir=memory_store_dir,
    )
    app.state.kinds["memory"] = make_memory_kind(memory_service)
    set_memory_service(memory_service)
    register_memory_builtin_tools(
        builtin_tools, resources=resource_svc, memory_service=memory_service
    )
    return store
