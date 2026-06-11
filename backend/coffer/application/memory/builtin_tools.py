"""Memory built-in MCP tools (spec 007).

Registered under the reserved ``coffer__`` prefix (added by the gateway). Tool
set: ``recall``, ``remember``, ``update_memory``, ``forget``, ``list_memory``.
``remember`` defaults to ``scope=project``; ``recall`` defaults to both scopes.

The agent's launch cwd (reported at session handshake) is threaded in as the
``cwd`` argument by the gateway in the surfaces phase; the handlers accept it so
project-scope resolution works. ``remember`` writes with ``actor="agent"``.
"""

from __future__ import annotations

from typing import Any

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.memory.scope import GLOBAL_STORE_NAME, project_store_name
from coffer.application.memory.service import MemoryService
from coffer.domain.memory.scope import MemoryScope

_MAX_TOP_K = 20
_MAX_QUERY_CHARS = 4096


def _scope_arg(args: dict[str, Any], *, default: MemoryScope | None) -> MemoryScope | None:
    raw = args.get("scope")
    if raw is None:
        return default
    if str(raw) == "project":
        return MemoryScope.PROJECT
    if str(raw) == "global":
        return MemoryScope.GLOBAL
    # A typo'd scope must not silently write to the wrong store.
    raise ValueError(f"unknown scope {raw!r}; expected 'project' or 'global'")


def register_memory_builtin_tools(
    registry: BuiltinToolRegistry,
    *,
    memory_service: MemoryService,
) -> None:
    """Wire the five memory tools into the gateway's registry."""

    async def recall(args: dict[str, Any]) -> dict[str, Any]:
        query = str(args["query"])[:_MAX_QUERY_CHARS]
        cwd = _cwd(args)
        scope = _scope_arg(args, default=None)  # None ⇒ span project + global
        top_k = _top_k_arg(args)
        mode = args.get("mode")
        hits, fallback = await memory_service.recall(
            cwd=cwd,
            query=query,
            scope=scope,
            top_k=top_k,
            mode=mode if mode in {"grep", "keyword", "vector"} else None,
        )
        return {
            "hits": [
                {
                    "id": h.id,
                    "text": h.text,
                    "score": h.score,
                    "source": h.source,
                    "time": h.time.isoformat(),
                }
                for h in hits
            ],
            # True when a vector request degraded to keyword (no embedding
            # configured) — the acceptance scenario requires the flag here too.
            "fallback": fallback,
        }

    async def remember(args: dict[str, Any]) -> dict[str, Any]:
        text = args.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("'text' must be a non-empty string")
        scope = _scope_arg(args, default=MemoryScope.PROJECT) or MemoryScope.PROJECT
        fact = await memory_service.add_fact(
            scope=scope,
            cwd=_cwd(args),
            name=str(args.get("name", "")),
            description=str(args.get("description", "")),
            body=text,
            actor="agent",
            type=str(args["type"]) if args.get("type") else None,
            origin_session_id=str(args["origin_session_id"])
            if args.get("origin_session_id")
            else None,
        )
        return {"id": fact.id, "name": fact.name, "scope": scope.value, "status": "created"}

    async def update_memory(args: dict[str, Any]) -> dict[str, Any]:
        fact_id = str(args["id"])
        text = args.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("'text' must be a non-empty string")
        store_name = await memory_service.find_fact_store(cwd=_cwd(args), fact_id=fact_id)
        fact = await memory_service.update_fact(
            store_name=store_name, fact_id=fact_id, new_body=text, actor="agent"
        )
        return {"id": fact.id, "status": "updated"}

    async def forget(args: dict[str, Any]) -> dict[str, Any]:
        fact_id = str(args["id"])
        store_name = await memory_service.find_fact_store(cwd=_cwd(args), fact_id=fact_id)
        await memory_service.delete_fact(store_name=store_name, fact_id=fact_id, actor="agent")
        return {"id": fact_id, "status": "forgotten"}

    async def list_memory(args: dict[str, Any]) -> dict[str, Any]:
        scope = _scope_arg(args, default=MemoryScope.PROJECT) or MemoryScope.PROJECT
        cwd = _cwd(args)
        resolved = await memory_service.resolve_scope(scope=scope, cwd=cwd)
        store_name = (
            GLOBAL_STORE_NAME if resolved.is_global else project_store_name(resolved.project_id)
        )
        facts, total = await memory_service.list_facts(store_name=store_name)
        return {
            "scope": resolved.scope.value,
            "total": total,
            "facts": [
                {
                    "id": f.id,
                    "name": f.name,
                    "description": f.description,
                    "type": f.type,
                    "actor": f.actor,
                }
                for f in facts
            ],
        }

    registry.register(
        BuiltinTool(
            name="recall",
            description="Recall relevant memory facts (spans project + global by default).",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "scope": {"type": "string", "enum": ["project", "global"]},
                    "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                    "mode": {"type": "string", "enum": ["grep", "keyword", "vector"]},
                    "cwd": {"type": "string", "description": "Agent launch cwd (session-injected)"},
                },
                "required": ["query"],
            },
            handler=recall,
        )
    )
    registry.register(
        BuiltinTool(
            name="remember",
            description="Record a fact in memory (defaults to project scope).",
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "scope": {"type": "string", "enum": ["project", "global"]},
                    "type": {"type": "string"},
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "cwd": {"type": "string"},
                },
                "required": ["text"],
            },
            handler=remember,
        )
    )
    registry.register(
        BuiltinTool(
            name="update_memory",
            description="Update a memory fact's text by id.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "cwd": {"type": "string"},
                },
                "required": ["id", "text"],
            },
            handler=update_memory,
        )
    )
    registry.register(
        BuiltinTool(
            name="forget",
            description="Delete a memory fact by id.",
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "cwd": {"type": "string"},
                },
                "required": ["id"],
            },
            handler=forget,
        )
    )
    registry.register(
        BuiltinTool(
            name="list_memory",
            description="List memory facts in a scope (default: project).",
            input_schema={
                "type": "object",
                "properties": {
                    "scope": {"type": "string", "enum": ["project", "global"]},
                    "cwd": {"type": "string"},
                },
                "required": [],
            },
            handler=list_memory,
        )
    )


def _top_k_arg(args: dict[str, Any]) -> int:
    try:
        value = int(args.get("top_k", 5))
    except (TypeError, ValueError) as exc:
        raise ValueError("'top_k' must be an integer") from exc
    return max(1, min(_MAX_TOP_K, value))


def _cwd(args: dict[str, Any]) -> str | None:
    raw = args.get("cwd")
    return str(raw) if isinstance(raw, str) and raw else None
