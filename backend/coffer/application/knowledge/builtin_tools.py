"""Knowledge built-in MCP tools — the retrieval half.

Registered under the reserved ``coffer__`` prefix (added by the gateway). This
module contributes ``search``, ``grep`` and ``read``; the sibling
``document_tools`` contributes ``list``, ``write`` and ``delete``. Six tools
over one kind, where there used to be twelve over two: an agent no longer has
to decide whether what it is after is "memory" or "knowledge" before it can ask
for it.

Every retrieval tool takes an optional ``scope``. Omitted, it resolves from the
agent's launch cwd (threaded in as ``cwd`` by the gateway at session handshake)
to that project's scope, falling back to ``global`` outside a project — so the
common case needs no argument at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.knowledge.scope import GLOBAL_SCOPE_NAME
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.knowledge.stores import scope_name_for
from coffer.domain.knowledge.scope import KnowledgeScope, scope_kind_of

_MAX_TOP_K = 20
_MAX_QUERY_CHARS = 4096
_MAX_MATCHES = 500

#: Shared JSON-schema fragment for the optional scope argument. Repeated in
#: every tool's schema so the description travels with the argument.
SCOPE_PROPERTY = {
    "type": "string",
    "description": (
        "Knowledge scope: 'global', a 'project-<id>' scope, or a named "
        "collection. Omit to use the current project's scope (falling back to "
        "'global' outside a project)."
    ),
}
CWD_PROPERTY = {"type": "string", "description": "Agent launch cwd (session-injected)."}


def _cwd(args: dict[str, Any]) -> str | None:
    raw = args.get("cwd")
    return str(raw) if isinstance(raw, str) and raw else None


def explicit_scope(args: dict[str, Any]) -> str | None:
    """The caller-supplied scope name, or ``None`` when it was left out."""
    raw = args.get("scope")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


async def resolve_scope_arg(svc: KnowledgeService, args: dict[str, Any]) -> str:
    """The scope a call operates on: the explicit one, else the cwd's project,
    else ``global``.

    Resolving the project scope provisions it, which is deliberate: an agent
    that wants to write something should not have to ask permission first."""
    named = explicit_scope(args)
    if named is not None:
        return named
    cwd = _cwd(args)
    if cwd is not None:
        try:
            resolved = await svc.resolve_scope(scope=KnowledgeScope.PROJECT, cwd=cwd)
        except Exception:
            # Not inside a git project (or the resolve failed): global still works.
            return GLOBAL_SCOPE_NAME
        return scope_name_for(resolved)
    return GLOBAL_SCOPE_NAME


async def ensure_writable_scope(svc: KnowledgeService, scope_name: str) -> None:
    """Provision an auto-scope before writing to it.

    A named collection is NOT provisioned here — it exists because someone
    created it deliberately, so an unknown name must be an error rather than a
    new empty collection conjured from a typo."""
    if scope_kind_of(scope_name) is not KnowledgeScope.NAMED:
        await svc.ensure_scope(scope_name)


def is_document(svc: KnowledgeService, scope_name: str, item_id: str) -> bool:
    """Whether an id names an ingested document rather than a written note.

    Both lanes index into the same table under one ``(kind, scope)``, so the
    index row cannot tell them apart — the file can. A document is the one with
    a file under the scope's ``docs/``; a note lives in ``notes/``. Getting this
    wrong would drop a row while leaving its markdown behind, and the
    reconciler would simply put the row back."""
    try:
        path, _folder = svc.doc_paths(scope_name=scope_name, document_id=item_id)
    except ValueError:
        return False  # not a safe path segment, so not a document id
    return Path(path).exists()


def top_k_arg(args: dict[str, Any], default: int = 5) -> int:
    try:
        value = int(args.get("top_k", default))
    except (TypeError, ValueError) as exc:
        raise ValueError("'top_k' must be an integer") from exc
    return max(1, min(_MAX_TOP_K, value))


def register_knowledge_builtin_tools(
    registry: BuiltinToolRegistry,
    *,
    knowledge_service: KnowledgeService,
) -> None:
    """Wire ``search`` / ``grep`` / ``read`` into the gateway's registry."""

    async def search(args: dict[str, Any]) -> dict[str, Any]:
        query = str(args["query"])[:_MAX_QUERY_CHARS]
        scope_name = await resolve_scope_arg(knowledge_service, args)
        await ensure_writable_scope(knowledge_service, scope_name)
        # An implicit scope also folds in ``global`` — knowledge filed globally
        # is meant to follow the user everywhere, so the default span is
        # project + global. An EXPLICIT scope is taken literally.
        span = "project" if explicit_scope(args) is not None else "both"
        # One query → one answer: the surface never selects a retrieval mode;
        # the service resolves it from the scope's ``default_mode`` and degrades
        # vector→keyword rather than erroring.
        hits, mode, fallback = await knowledge_service.recall_in_scope(
            scope_name=scope_name,
            query=query,
            top_k=top_k_arg(args),
            mode=None,
            scope=span,  # type: ignore[arg-type]
        )
        return {
            "scope": scope_name,
            "mode": mode,
            "degraded": fallback,
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
        }

    async def grep(args: dict[str, Any]) -> dict[str, Any]:
        pattern = str(args["pattern"])
        scope_name = await resolve_scope_arg(knowledge_service, args)
        await ensure_writable_scope(knowledge_service, scope_name)
        try:
            max_matches = max(1, min(_MAX_MATCHES, int(args.get("max_matches", 200))))
        except (TypeError, ValueError) as exc:
            raise ValueError("'max_matches' must be an integer") from exc
        result = await knowledge_service.grep(
            scope_name=scope_name, pattern=pattern, max_matches=max_matches
        )
        return {
            "scope": scope_name,
            "hits": [
                {"path": h.path, "line_number": h.line_number, "line": h.line} for h in result.hits
            ],
            "truncated": result.truncated,
        }

    async def read(args: dict[str, Any]) -> dict[str, Any]:
        item_id = str(args["id"])
        scope_name = await resolve_scope_arg(knowledge_service, args)
        await ensure_writable_scope(knowledge_service, scope_name)
        if not is_document(knowledge_service, scope_name, item_id):
            entry, path = await knowledge_service.get_fact_with_path(
                scope_name=scope_name, fact_id=item_id
            )
            return {
                "scope": scope_name,
                "id": entry.id,
                "type": "entry",
                "title": entry.title,
                "description": entry.description,
                "path": path,
                "text": entry.body,
            }
        doc, markdown = await knowledge_service.read_document(
            scope_name=scope_name, document_id=item_id
        )
        return {
            "scope": scope_name,
            "id": doc.id,
            "type": "document",
            "title": doc.title,
            "description": doc.description,
            "source_mode": doc.source_mode,
            "text": markdown,
        }

    registry.register(
        BuiltinTool(
            name="search",
            description=(
                "Search Coffer's knowledge for whatever is relevant to a query — "
                "both the notes agents and the user have written down and the "
                "documents that were ingested; they live in one place, so one "
                "search covers both. Semantic, keyword or hybrid depending on "
                "how the scope is configured, chosen for you. Returns ranked "
                "snippets with the id and file each came from; pass an id to "
                "coffer__read for the full text. Reach for this before asking "
                "the user something they may already have told Coffer."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What you are looking for."},
                    "scope": SCOPE_PROPERTY,
                    "top_k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                    "cwd": CWD_PROPERTY,
                },
                "required": ["query"],
            },
            handler=search,
        )
    )
    registry.register(
        BuiltinTool(
            name="grep",
            description=(
                "Run a literal or regular-expression search over every Markdown "
                "file in a knowledge scope, returning matching lines with their "
                "file and line number. Use this when you need exact matches — an "
                "identifier, a path, a CJK phrase a tokenizer would split — and "
                "coffer__search when you want relevance."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Literal text or regex."},
                    "scope": SCOPE_PROPERTY,
                    "max_matches": {
                        "type": "integer",
                        "default": 200,
                        "minimum": 1,
                        "maximum": 500,
                    },
                    "cwd": CWD_PROPERTY,
                },
                "required": ["pattern"],
            },
            handler=grep,
        )
    )
    registry.register(
        BuiltinTool(
            name="read",
            description=(
                "Read one knowledge item in full by its id — the whole Markdown, "
                "not the snippet a search returned. Works for either kind of "
                "item: an ingested document or an entry someone wrote, resolved "
                "automatically, so you can hand it any id coffer__search or "
                "coffer__list gave you."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Document or entry id (from search / list).",
                    },
                    "scope": SCOPE_PROPERTY,
                    "cwd": CWD_PROPERTY,
                },
                "required": ["id"],
            },
            handler=read,
        )
    )
