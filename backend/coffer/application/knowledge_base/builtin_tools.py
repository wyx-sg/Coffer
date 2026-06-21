"""KB built-in MCP tools — read AND write (documents are co-managed, ADR-028).

Registered into ``BuiltinToolRegistry`` at startup under the reserved
``coffer__`` prefix (added by the gateway on list). Tool set:

- read: ``list_knowledge_bases``, ``search_knowledge``, ``grep_knowledge``,
  ``read_document``;
- write: ``add_document``, ``edit_document``, ``delete_document``.

The write tools share the REST surface's service paths, so they record the F01
audit trail with the agent as actor.
"""

from __future__ import annotations

from typing import Any

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.knowledge_base.service import KnowledgeBaseService
from coffer.application.resource_service import ResourceService

# MCP callers send free-form JSON; mirror the surface-layer ceilings so an agent
# cannot bypass them by hand-rolling the tool call.
_MAX_TOP_K = 20
_MAX_QUERY_CHARS = 4096
_MAX_MATCHES = 500

# Audit actor for agent-side document writes (the document-level F01 trail; the
# per-call mcp_invocations row is recorded separately by the gateway). The upload
# size ceiling is enforced by the KB's ``max_document_bytes`` config in the service.
_AGENT_ACTOR = "agent"


def register_kb_builtin_tools(
    registry: BuiltinToolRegistry,
    *,
    resources: ResourceService,
    kb_service: KnowledgeBaseService,
) -> None:
    """Wire the four read-only KB tools into the gateway's registry."""

    async def list_knowledge_bases(_args: dict[str, Any]) -> dict[str, Any]:
        kbs = await resources.list(kind="knowledge_base")
        results = []
        for kb in kbs:
            metrics = await kb_service.metrics(kb_name=kb.name)
            results.append(
                {
                    "name": kb.name,
                    "description": kb.description,
                    "document_count": metrics["document_count"],
                    "disk_bytes": metrics["disk_bytes"],
                    "enabled_modes": metrics["enabled_modes"],
                }
            )
        return {"knowledge_bases": results}

    async def search_knowledge(args: dict[str, Any]) -> dict[str, Any]:
        kb = str(args["kb"])
        query = str(args["query"])[:_MAX_QUERY_CHARS]
        top_k = max(1, min(_MAX_TOP_K, int(args.get("top_k", 5))))
        # One query → one answer: the surface never selects a mode; the service
        # resolves it from the store's default_mode (mode stays internal).
        result = await kb_service.search(
            kb_name=kb,
            query=query,
            top_k=top_k,
            mode=None,
        )
        return {
            "passages": [
                {
                    "document_id": p.document_id,
                    "title": p.title,
                    "text": p.text,
                    "score": p.score,
                    "position": p.position,
                }
                for p in result.passages
            ],
        }

    async def grep_knowledge(args: dict[str, Any]) -> dict[str, Any]:
        kb = str(args["kb"])
        pattern = str(args["pattern"])
        max_matches = max(1, min(_MAX_MATCHES, int(args.get("max_matches", 200))))
        result = await kb_service.grep(kb_name=kb, pattern=pattern, max_matches=max_matches)
        return {
            "hits": [
                {"path": h.path, "line_number": h.line_number, "line": h.line} for h in result.hits
            ],
            "truncated": result.truncated,
        }

    async def read_document(args: dict[str, Any]) -> dict[str, Any]:
        kb = str(args["kb"])
        document_id = str(args["document_id"])
        doc, markdown = await kb_service.read_document(kb_name=kb, document_id=document_id)
        return {
            "document_id": doc.id,
            "title": doc.title,
            "source_mode": doc.source_mode,
            "markdown": markdown,
        }

    # ----- write tools (documents are co-managed — ADR-028) -----
    # Every write funnels through the same service paths as the REST surface, so
    # it records the F01 audit. The acting agent is the audit actor.

    async def add_document(args: dict[str, Any]) -> dict[str, Any]:
        kb = str(args["kb"])
        filename = str(args["filename"])
        content = str(args["content"])
        replace = bool(args.get("replace", False))
        doc = await kb_service.ingest_bytes(
            kb_name=kb,
            filename=filename,
            raw_bytes=content.encode("utf-8"),
            actor=_AGENT_ACTOR,
            replace=replace,
        )
        return {
            "document_id": doc.id,
            "title": doc.title,
            "source_mode": doc.source_mode,
        }

    async def edit_document(args: dict[str, Any]) -> dict[str, Any]:
        kb = str(args["kb"])
        document_id = str(args["document_id"])
        content = str(args["content"])
        doc = await kb_service.edit_document(
            kb_name=kb, document_id=document_id, new_markdown=content, actor=_AGENT_ACTOR
        )
        return {
            "document_id": doc.id,
            "title": doc.title,
            "source_mode": doc.source_mode,
        }

    async def delete_document(args: dict[str, Any]) -> dict[str, Any]:
        kb = str(args["kb"])
        document_id = str(args["document_id"])
        await kb_service.delete_document(kb_name=kb, document_id=document_id, actor=_AGENT_ACTOR)
        return {"deleted": True, "document_id": document_id}

    registry.register(
        BuiltinTool(
            name="list_knowledge_bases",
            description="List every knowledge base registered in Coffer.",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=list_knowledge_bases,
        )
    )
    registry.register(
        BuiltinTool(
            name="search_knowledge",
            description=(
                "Search a knowledge base for relevant passages. Returns ranked "
                "passages with their source document id, title, and score."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "kb": {"type": "string", "description": "Knowledge base name"},
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                },
                "required": ["kb", "query"],
            },
            handler=search_knowledge,
        )
    )
    registry.register(
        BuiltinTool(
            name="grep_knowledge",
            description="Run a ripgrep pattern over a knowledge base's markdown files.",
            input_schema={
                "type": "object",
                "properties": {
                    "kb": {"type": "string"},
                    "pattern": {"type": "string"},
                    "max_matches": {
                        "type": "integer",
                        "default": 200,
                        "minimum": 1,
                        "maximum": 500,
                    },
                },
                "required": ["kb", "pattern"],
            },
            handler=grep_knowledge,
        )
    )
    registry.register(
        BuiltinTool(
            name="read_document",
            description="Read a knowledge base document's full Markdown (frontmatter + body).",
            input_schema={
                "type": "object",
                "properties": {
                    "kb": {"type": "string"},
                    "document_id": {"type": "string"},
                },
                "required": ["kb", "document_id"],
            },
            handler=read_document,
        )
    )
    registry.register(
        BuiltinTool(
            name="add_document",
            description=(
                "Add a Markdown document to a knowledge base (documents are "
                "co-managed). Provide the Markdown body as 'content' and a "
                "filename with an extension (e.g. 'notes.md'). Re-using a filename "
                "already in the KB updates that document in place only when "
                "replace=true; identical content is a no-op."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "kb": {"type": "string", "description": "Knowledge base name"},
                    "filename": {
                        "type": "string",
                        "description": "Document filename including an extension, e.g. 'notes.md'",
                    },
                    "content": {"type": "string", "description": "The Markdown body"},
                    "replace": {
                        "type": "boolean",
                        "default": False,
                        "description": "Update an existing same-named document in place",
                    },
                },
                "required": ["kb", "filename", "content"],
            },
            handler=add_document,
        )
    )
    registry.register(
        BuiltinTool(
            name="edit_document",
            description=("Replace a knowledge base document's Markdown body (marks it 'edited')."),
            input_schema={
                "type": "object",
                "properties": {
                    "kb": {"type": "string"},
                    "document_id": {"type": "string"},
                    "content": {"type": "string", "description": "The new Markdown body"},
                },
                "required": ["kb", "document_id", "content"],
            },
            handler=edit_document,
        )
    )
    registry.register(
        BuiltinTool(
            name="delete_document",
            description=("Delete a document from a knowledge base."),
            input_schema={
                "type": "object",
                "properties": {
                    "kb": {"type": "string"},
                    "document_id": {"type": "string"},
                },
                "required": ["kb", "document_id"],
            },
            handler=delete_document,
        )
    )
