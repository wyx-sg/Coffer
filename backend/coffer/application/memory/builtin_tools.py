"""Memory built-in MCP tools (spec 007).

Registered under the reserved ``coffer__`` prefix (added by the gateway). Tool
set: ``recall``, ``remember``, ``list_memory``, ``set_handoff``, ``resume``.
``remember`` defaults to ``scope=project``; ``recall`` defaults to both scopes.
The agent's write surface is ``remember`` + the internal organizer — there is no
``update_memory``/``forget`` (humans correct memory via the REST/CLI surface or
their own editor, files-as-truth).

The agent's launch cwd (reported at session handshake) is threaded in as the
``cwd`` argument by the gateway in the surfaces phase; the handlers accept it so
project-scope resolution works. ``remember`` writes with ``actor="agent"``.
"""

from __future__ import annotations

from typing import Any

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.memory.handoff import HandoffService
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
    handoff_service: HandoffService,
) -> None:
    """Wire the memory tools (recall/remember/list + handoff) into the gateway's
    registry."""

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

    async def set_handoff(args: dict[str, Any]) -> dict[str, Any]:
        body = args.get("body") or args.get("text")
        if not isinstance(body, str) or not body.strip():
            raise ValueError("handoff 'body' must be a non-empty string")
        res = await handoff_service.set_handoff(cwd=_cwd(args), body=body, actor="agent")
        return {"status": "saved", "branch": res.branch, "scope": "project"}

    async def resume(args: dict[str, Any]) -> dict[str, Any]:
        res = await handoff_service.resume(cwd=_cwd(args))
        if res is None:
            return {"found": False}
        ts = res.updated_at.isoformat()
        return {
            "found": True,
            "branch": res.branch,
            "body": res.body,
            "updated_at": ts,
            # Freshness annotation: a resumed scene may be stale; the agent
            # should weigh it against the current request, not blindly continue.
            # Chinese prose for the agent — fullwidth punctuation is intentional.
            "note": f"现场，截至 {ts}，可能已过期；无关请忽略。",  # noqa: RUF001
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
    registry.register(
        BuiltinTool(
            name="set_handoff",
            description=(
                "Save the current working state ('现场': current task, next steps, "
                "files in flight, open questions) for the current project + git branch. "
                "Overwrites the previous handoff for this branch. Call when pausing work."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "body": {
                        "type": "string",
                        "description": (
                            "Current task / next steps / files in flight / open questions."
                        ),
                    },
                    "cwd": {"type": "string", "description": "Working directory (auto-injected)."},
                },
                "required": ["body"],
            },
            handler=set_handoff,
        )
    )
    registry.register(
        BuiltinTool(
            name="resume",
            description=(
                "Return the saved working-state handoff for the current project + git "
                "branch, to continue where work left off. Returns found=false if none."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "cwd": {"type": "string", "description": "Working directory (auto-injected)."}
                },
            },
            handler=resume,
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
