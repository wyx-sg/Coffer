"""KB built-in MCP tools — read-only (the KB is agent-read-only).

Registered into ``BuiltinToolRegistry`` at startup under the reserved
``coffer__`` prefix (added by the gateway on list). Tool set:
``list_knowledge_bases``, ``search_knowledge``, ``grep_knowledge``,
``read_document``. No write tool exists for KBs.
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
        mode = args.get("mode")
        result = await kb_service.search(
            kb_name=kb,
            query=query,
            top_k=top_k,
            mode=mode if mode in {"keyword", "vector"} else None,
        )
        return {
            "mode": result.mode,
            "fallback": result.fallback,
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
        hits = await kb_service.grep(kb_name=kb, pattern=pattern, max_matches=max_matches)
        return {
            "hits": [{"path": h.path, "line_number": h.line_number, "line": h.line} for h in hits]
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
                    "mode": {"type": "string", "enum": ["keyword", "vector"]},
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
