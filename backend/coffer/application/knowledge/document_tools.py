"""Knowledge built-in MCP tools — enumerate and change what is stored.

The write half of the six (``list``, ``write``, ``delete``); the retrieval half
lives in ``builtin_tools``. Split across two modules only for the project's
file-size ceiling — one kind, one tool family.

Every write funnels through the same service paths as the REST surface.
Documents are co-managed (spec knowledge FR-062): an agent may add and edit them, not
only read them.
"""

from __future__ import annotations

from typing import Any, Literal

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.knowledge.builtin_tools import (
    CWD_PROPERTY,
    SCOPE_PROPERTY,
    ensure_writable_scope,
    explicit_scope,
    is_document,
    resolve_scope_arg,
)
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.resource_service import ResourceService
from coffer.domain.knowledge.document import KIND_KNOWLEDGE

# MCP callers send free-form JSON; mirror the surface-layer ceilings so an agent
# cannot bypass them by hand-rolling the tool call. The upload size ceiling is
# enforced by ``max_document_bytes`` in the scope's config, in the service.
_MAX_LIST = 200

#: Audit actor for agent-side writes (the item-level F01 trail; the per-call
#: mcp_invocations row is recorded separately by the gateway).
#: The MCP tools always write as the agent; typed as the literal so the
#: service's ``actor`` parameter keeps its two-value guarantee.
_AGENT_ACTOR: Literal["agent"] = "agent"


def _limit(args: dict[str, Any], default: int = 50) -> int:
    try:
        value = int(args.get("limit", default))
    except (TypeError, ValueError) as exc:
        raise ValueError("'limit' must be an integer") from exc
    return max(1, min(_MAX_LIST, value))


def register_document_builtin_tools(
    registry: BuiltinToolRegistry,
    *,
    resources: ResourceService,
    knowledge_service: KnowledgeService,
) -> None:
    """Wire ``list`` / ``write`` / ``delete`` into the gateway's registry."""

    async def list_knowledge(args: dict[str, Any]) -> dict[str, Any]:
        if explicit_scope(args) is None and not args.get("all"):
            # No scope named and no explicit request for the catalogue: show what
            # is in the scope this session is working in.
            return await _list_one(await resolve_scope_arg(knowledge_service, args), args)
        named = explicit_scope(args)
        if named is not None:
            return await _list_one(named, args)
        return await _list_scopes()

    async def _list_scopes() -> dict[str, Any]:
        out = []
        for r in await resources.list(kind=KIND_KNOWLEDGE):
            try:
                entries = await knowledge_service.fact_count(scope_name=r.name)
                documents = await knowledge_service.document_count(scope_name=r.name)
            except Exception:
                entries, documents = 0, 0
            out.append(
                {
                    "scope": r.name,
                    "description": r.description,
                    "entry_count": entries,
                    "document_count": documents,
                }
            )
        return {"scopes": out}

    async def _list_one(scope_name: str, args: dict[str, Any]) -> dict[str, Any]:
        await ensure_writable_scope(knowledge_service, scope_name)
        limit = _limit(args)
        entries, entry_total = await knowledge_service.list_facts(
            scope_name=scope_name, limit=limit
        )
        documents, doc_total = await knowledge_service.list_documents(
            scope_name=scope_name, limit=limit, offset=0
        )
        return {
            "scope": scope_name,
            "entry_total": entry_total,
            "document_total": doc_total,
            "entries": [
                {
                    "id": e.id,
                    "title": e.title,
                    "description": e.description,
                    "actor": e.actor,
                }
                for e in entries
            ],
            "documents": [
                {"id": d.id, "title": d.title, "source_mode": d.source_mode} for d in documents
            ],
        }

    async def write(args: dict[str, Any]) -> dict[str, Any]:
        text = args.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("'text' must be a non-empty string")
        scope_name = await resolve_scope_arg(knowledge_service, args)
        await ensure_writable_scope(knowledge_service, scope_name)
        document_id = args.get("id")
        filename = args.get("filename")

        if isinstance(document_id, str) and document_id:
            # Update in place, in whichever lane the id lives in — the caller
            # need not know which kind of item it named.
            if not is_document(knowledge_service, scope_name, str(document_id)):
                entry = await knowledge_service.update_fact(
                    scope_name=scope_name,
                    fact_id=str(document_id),
                    new_body=text,
                    actor=_AGENT_ACTOR,
                    new_title=args.get("title"),
                    new_description=args.get("description"),
                )
                return {
                    "scope": scope_name,
                    "id": entry.id,
                    "type": "entry",
                    "title": entry.title,
                    "status": "updated",
                }
            doc = await knowledge_service.edit_document(
                scope_name=scope_name,
                document_id=str(document_id),
                new_markdown=text,
                actor=_AGENT_ACTOR,
            )
            return {
                "scope": scope_name,
                "id": doc.id,
                "type": "document",
                "title": doc.title,
                "source_mode": doc.source_mode,
                "status": "updated",
            }

        if isinstance(filename, str) and filename:
            # A filename means "this is a document". Re-using a filename already
            # in the scope updates that document in place; identical bytes are a
            # no-op (spec knowledge FR-062).
            doc = await knowledge_service.ingest_bytes(
                scope_name=scope_name,
                filename=filename,
                raw_bytes=text.encode("utf-8"),
                actor=_AGENT_ACTOR,
                replace=True,
            )
            return {
                "scope": scope_name,
                "id": doc.id,
                "type": "document",
                "title": doc.title,
                "source_mode": doc.source_mode,
                "status": "written",
            }

        # ``name`` is the deprecated alias of ``title`` — accept it so live agent
        # calls keep working; ``title`` wins when both are sent.
        entry = await knowledge_service.add_fact_to_scope(
            scope_name=scope_name,
            title=str(args.get("title") or args.get("name", "")),
            description=str(args.get("description", "")),
            body=text,
            actor=_AGENT_ACTOR,
            origin_session_id=(
                str(args["origin_session_id"]) if args.get("origin_session_id") else None
            ),
        )
        return {
            "scope": scope_name,
            "id": entry.id,
            "type": "entry",
            "title": entry.title,
            "status": "created",
        }

    async def delete(args: dict[str, Any]) -> dict[str, Any]:
        item_id = str(args["id"])
        scope_name = await resolve_scope_arg(knowledge_service, args)
        await ensure_writable_scope(knowledge_service, scope_name)
        if not is_document(knowledge_service, scope_name, item_id):
            await knowledge_service.delete_fact(
                scope_name=scope_name, fact_id=item_id, actor=_AGENT_ACTOR
            )
            return {"deleted": True, "scope": scope_name, "id": item_id, "type": "entry"}
        await knowledge_service.delete_document(
            scope_name=scope_name, document_id=item_id, actor=_AGENT_ACTOR
        )
        return {"deleted": True, "scope": scope_name, "id": item_id, "type": "document"}

    registry.register(
        BuiltinTool(
            name="list",
            description=(
                "List what Coffer knows. With no arguments, lists the current "
                "project's scope: the entries written into it and the documents "
                "ingested into it, with their ids. Pass a scope to list that one "
                "instead, or all=true for the catalogue of every scope with its "
                "counts. Use it to see what exists before writing something that "
                "may already be there."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "scope": SCOPE_PROPERTY,
                    "all": {
                        "type": "boolean",
                        "default": False,
                        "description": "List every scope instead of one scope's contents.",
                    },
                    "limit": {"type": "integer", "default": 50, "minimum": 1, "maximum": 200},
                    "cwd": CWD_PROPERTY,
                },
                "required": [],
            },
            handler=list_knowledge,
        )
    )
    registry.register(
        BuiltinTool(
            name="write",
            description=(
                "Record something in Coffer so it survives this session and is "
                "there for the next agent. With just 'text' (plus a short "
                "'title') it files an entry — a fact, decision, or preference "
                "worth remembering. With 'filename' it stores a Markdown "
                "document, replacing any same-named one. With 'id' it rewrites "
                "an existing entry or document in full. Defaults to the current "
                "project's scope; pass scope='global' for things true everywhere."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The content: the fact to record, or the Markdown body.",
                    },
                    "title": {"type": "string", "description": "Short title for the item."},
                    "description": {"type": "string", "description": "One-line summary."},
                    "filename": {
                        "type": "string",
                        "description": (
                            "Store as a document under this filename (with extension, "
                            "e.g. 'design-notes.md') instead of as an entry."
                        ),
                    },
                    "id": {
                        "type": "string",
                        "description": "Rewrite this existing entry or document instead.",
                    },
                    "name": {"type": "string", "description": "Deprecated alias of 'title'."},
                    "scope": SCOPE_PROPERTY,
                    "cwd": CWD_PROPERTY,
                },
                "required": ["text"],
            },
            handler=write,
        )
    )
    registry.register(
        BuiltinTool(
            name="delete",
            description=(
                "Delete one knowledge item by id — an entry or an ingested "
                "document, resolved automatically. The Markdown file goes with "
                "it; this is not reversible from here."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Document or entry id."},
                    "scope": SCOPE_PROPERTY,
                    "cwd": CWD_PROPERTY,
                },
                "required": ["id"],
            },
            handler=delete,
        )
    )
