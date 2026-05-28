"""KB built-in MCP tools — registered into BuiltinToolRegistry at startup."""

from __future__ import annotations

from typing import Any

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.knowledge_base.service import KnowledgeBaseService
from coffer.application.resource_service import ResourceService

# MCP callers send free-form JSON; the surface-layer Pydantic bounds applied
# to ``SearchRequest`` are NOT in play here. Enforce the same ceilings in the
# handler so an agent cannot bypass them by hand-rolling the tool call
# (CODE22-013).
_MAX_TOP_K = 20
_MAX_QUERY_CHARS = 4096


def register_kb_builtin_tools(
    registry: BuiltinToolRegistry,
    *,
    resources: ResourceService,
    kb_service: KnowledgeBaseService,
) -> None:
    """Wire the three KB tools into the gateway's built-in registry."""

    async def list_knowledge_bases(_args: dict[str, Any]) -> dict[str, Any]:
        kbs = await resources.list(kind="knowledge_base")
        results = []
        for kb in kbs:
            # ``metrics`` walks the on-disk KB dir under the hood; the walk is
            # offloaded to a worker thread inside the service so it cannot
            # stall the event loop while listing every KB (CODE22-014).
            count, disk = await kb_service.metrics(kb_name=kb.name)
            results.append(
                {
                    "name": kb.name,
                    "description": kb.description,
                    "document_count": count,
                    "disk_bytes": disk,
                    "embedding_model": kb.config.get("embedding_model"),
                }
            )
        return {"knowledge_bases": results}

    async def search_knowledge_base(args: dict[str, Any]) -> dict[str, Any]:
        kb = str(args["kb"])
        query = str(args["query"])[:_MAX_QUERY_CHARS]
        raw_top_k = int(args.get("top_k", 5))
        top_k = max(1, min(_MAX_TOP_K, raw_top_k))
        hits = await kb_service.search(kb_name=kb, query=query, top_k=top_k)
        return {
            "hits": [
                {
                    "text": h.text,
                    "document_id": h.document_id,
                    "filename": h.filename,
                    "score": h.score,
                    "position": h.position,
                }
                for h in hits
            ]
        }

    async def get_document(args: dict[str, Any]) -> dict[str, Any]:
        kb = str(args["kb"])
        document_id = str(args["document_id"])
        doc, text = await kb_service.get_document_text(kb_name=kb, document_id=document_id)
        return {
            "document_id": doc.id,
            "filename": doc.filename,
            "size_bytes": doc.size_bytes,
            "text": text,
        }

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
            name="search_knowledge_base",
            description=(
                "Search a knowledge base. Returns ranked passages with their "
                "source document id, filename, and a relevance score."
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
            handler=search_knowledge_base,
        )
    )
    registry.register(
        BuiltinTool(
            name="get_document",
            description="Fetch a document's full extracted text and metadata.",
            input_schema={
                "type": "object",
                "properties": {
                    "kb": {"type": "string"},
                    "document_id": {"type": "string"},
                },
                "required": ["kb", "document_id"],
            },
            handler=get_document,
        )
    )
