"""Wiring for the one ``knowledge`` kind.

Short, now that the kind is a directory: one service, five built-in tools, one
Kind. There is no substrate to build, no reconciler to hold, no reindex sweep
to run at boot — with the files as the only truth there is nothing derived that
could be stale (ADR knowledge-is-plain-files).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coffer.application.builtin_tools import BuiltinToolRegistry
from coffer.application.knowledge.builtin_tools import register_knowledge_builtin_tools
from coffer.application.knowledge.kind import make_knowledge_kind
from coffer.application.knowledge.service import KIND_KNOWLEDGE, KnowledgeService
from coffer.surfaces.http.dependencies import set_knowledge_service

if TYPE_CHECKING:
    from fastapi import FastAPI

    from coffer.application.audit_service import AuditService
    from coffer.application.resource_service import ResourceService


def wire_knowledge_kind(
    app: FastAPI,
    resource_svc: ResourceService,
    audit: AuditService,
    builtin_tools: BuiltinToolRegistry,
) -> KnowledgeService:
    """Wire the ``knowledge`` kind into the app and return its one service."""
    service = KnowledgeService(resources=resource_svc, audit=audit)
    set_knowledge_service(service)
    register_knowledge_builtin_tools(builtin_tools, knowledge_service=service)
    app.state.kinds[KIND_KNOWLEDGE] = make_knowledge_kind(service)
    return service
