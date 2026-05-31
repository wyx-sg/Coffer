"""Memory built-in MCP tools."""

from __future__ import annotations

from typing import Any

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.memory.service import MemoryService
from coffer.application.resource_service import ResourceService


def register_memory_builtin_tools(
    registry: BuiltinToolRegistry,
    *,
    resources: ResourceService,
    memory_service: MemoryService,
) -> None:
    async def list_memory_stores(_args: dict[str, Any]) -> dict[str, Any]:
        stores = await resources.list(kind="memory")
        out = []
        for s in stores:
            count, _disk = await memory_service.metrics(store_name=s.name)
            out.append(
                {
                    "name": s.name,
                    "description": s.description,
                    "memory_count": count,
                    "embedding_model": s.config.get("embedding_model"),
                }
            )
        return {"memory_stores": out}

    async def add_memory(args: dict[str, Any]) -> dict[str, Any]:
        store = str(args["store"])
        # CODE26-004: enforce minimal input shape locally — surface validators
        # (HTTP layer) re-validate text length against the store config, but
        # the MCP tools route through ``memory_service.add`` directly without
        # the FastAPI body schema, so guard non-string / empty inputs here.
        raw_text = args.get("text")
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise ValueError("'text' must be a non-empty string")
        record = await memory_service.add(store_name=store, text=raw_text, actor="agent")
        return {"id": record.id, "text": record.text, "status": "created"}

    async def search_memory(args: dict[str, Any]) -> dict[str, Any]:
        store = str(args["store"])
        query = str(args["query"])
        # CODE26-004: clamp ``top_k`` into the contracted range [1, 20] so a
        # rogue agent cannot ask the vector index for a 1M-row scan.
        top_k = max(1, min(20, int(args.get("top_k", 5))))
        hits = await memory_service.search(store_name=store, query=query, top_k=top_k)
        return {
            "hits": [
                {
                    "id": h.id,
                    "text": h.text,
                    "score": h.score,
                    "created_at": h.created_at.isoformat(),
                }
                for h in hits
            ]
        }

    async def delete_memory(args: dict[str, Any]) -> dict[str, Any]:
        store = str(args["store"])
        memory_id = str(args["memory_id"])
        await memory_service.delete(store_name=store, memory_id=memory_id, actor="agent")
        return {"deleted": True}

    registry.register(
        BuiltinTool(
            name="list_memory_stores",
            description="List every memory store registered in Coffer.",
            input_schema={"type": "object", "properties": {}, "required": []},
            handler=list_memory_stores,
        )
    )
    registry.register(
        BuiltinTool(
            name="add_memory",
            description="Record a memory (fact / preference / observation) in a store.",
            input_schema={
                "type": "object",
                "properties": {
                    "store": {"type": "string"},
                    "text": {"type": "string"},
                },
                "required": ["store", "text"],
            },
            handler=add_memory,
        )
    )
    registry.register(
        BuiltinTool(
            name="search_memory",
            description="Search a memory store for relevant memories.",
            input_schema={
                "type": "object",
                "properties": {
                    "store": {"type": "string"},
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                },
                "required": ["store", "query"],
            },
            handler=search_memory,
        )
    )
    registry.register(
        BuiltinTool(
            name="delete_memory",
            description="Delete a single memory by id.",
            input_schema={
                "type": "object",
                "properties": {
                    "store": {"type": "string"},
                    "memory_id": {"type": "string"},
                },
                "required": ["store", "memory_id"],
            },
            handler=delete_memory,
        )
    )
