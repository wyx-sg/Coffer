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
from coffer.infrastructure.observability import make_tracer
from coffer.surfaces.http.dependencies import set_kb_service

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
