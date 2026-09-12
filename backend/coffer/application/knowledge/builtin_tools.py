"""The knowledge layer's five built-in MCP tools.

``list``, ``grep``, ``read``, ``write``, ``delete`` — registered under the
reserved ``coffer__`` prefix the gateway adds (spec knowledge FR-040). There is
deliberately no ``search``: with no ranked index behind it, it would be a
second name for ``grep``, and "is this search or grep?" is a guess an agent
should never have to make (FR-024).

The motion these tools are shaped around is **catalogue, then grep**. ``list``
walks the directory one level at a time so an agent can choose *which file*
from titles and descriptions; ``grep`` finds *which line* once it knows where
to look. Neither takes a scope, a mode or a ``top_k``, because none exists: a
call spans every collection the agent is authorized for (FR-012), and that
authorization is the only argument the layer resolves for itself — threaded in
as ``agent`` by the gateway at session handshake, the same way ``cwd`` reaches
the tools that declare it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.knowledge.entry import CatalogueLevel, KnowledgeFile
from coffer.infrastructure.knowledge.grep import DEFAULT_MAX_MATCHES

_MAX_MATCHES = 500

#: Audit actor for an agent-side write when the session reported no identity.
_ANONYMOUS_ACTOR = "agent"

Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

#: Shared JSON-schema fragment for the session-injected caller identity. It is
#: declared on every knowledge tool because every one of them is authorized
#: per agent; the gateway fills it in and a caller never needs to.
AGENT_PROPERTY = {
    "type": "string",
    "description": "Calling agent's identity (session-injected; omit it).",
}


def _text(value: Any) -> str:
    """A trimmed string, or empty for anything that is not usable text."""
    return value.strip() if isinstance(value, str) else ""


def _required(args: dict[str, Any], name: str) -> str:
    value = _text(args.get(name))
    if not value:
        raise ValueError(f"{name!r} must be a non-empty string")
    return value


def _agent(args: dict[str, Any]) -> str | None:
    """The session's agent identity, or ``None`` when it reported none.

    ``None`` means "unidentified caller", which the service answers with the
    collections scoped to every agent — not with all of them.
    """
    return _text(args.get("agent")) or None


def _level_payload(level: CatalogueLevel) -> dict[str, Any]:
    return {
        "path": level.path,
        "directories": [
            {"path": d.path, "name": d.name, "file_count": d.file_count} for d in level.directories
        ],
        "files": [
            {
                "path": f.path,
                "title": f.title,
                "description": f.description,
                "actor": f.actor,
                "updated_at": f.updated_at,
            }
            for f in level.files
        ],
    }


def _file_payload(file: KnowledgeFile) -> dict[str, Any]:
    return {
        "path": file.path,
        "title": file.title,
        "description": file.description,
        "actor": file.actor,
        "created_at": file.created_at,
        "updated_at": file.updated_at,
        "body": file.body,
        "file_path": file.file_path,
        "folder_path": file.folder_path,
    }


def register_knowledge_builtin_tools(
    registry: BuiltinToolRegistry,
    *,
    knowledge_service: KnowledgeService,
) -> None:
    """Wire the five knowledge tools into the gateway's registry."""

    svc = knowledge_service

    async def list_knowledge(args: dict[str, Any]) -> dict[str, Any]:
        agent = _agent(args)
        path = _text(args.get("path"))
        if not path:
            collections = await svc.list_collections(agent)
            return {
                "collections": [
                    {"name": c.name, "description": c.description, "file_count": c.file_count}
                    for c in collections
                ]
            }
        return _level_payload(await svc.list_level(path, agent))

    async def grep(args: dict[str, Any]) -> dict[str, Any]:
        pattern = _required(args, "pattern")
        try:
            max_matches = int(args.get("max_matches", DEFAULT_MAX_MATCHES))
        except (TypeError, ValueError) as exc:
            raise ValueError("'max_matches' must be an integer") from exc
        outcome = await svc.grep(
            pattern,
            agent=_agent(args),
            collection=_text(args.get("collection")) or None,
            max_matches=max(1, min(_MAX_MATCHES, max_matches)),
        )
        return {
            "matches": [
                {"path": m.path, "line_number": m.line_number, "line": m.line}
                for m in outcome.matches
            ],
            "truncated": outcome.truncated,
        }

    async def read(args: dict[str, Any]) -> dict[str, Any]:
        return _file_payload(await svc.read(_required(args, "path"), _agent(args)))

    async def write(args: dict[str, Any]) -> dict[str, Any]:
        directory = _text(args.get("directory"))
        relpath = _text(args.get("path"))
        if bool(directory) == bool(relpath):
            raise ValueError(
                "a write takes exactly one of 'directory' (create a new file "
                "there) or 'path' (replace that file)"
            )
        agent = _agent(args)
        written = await svc.write(
            title=_required(args, "title"),
            description=_required(args, "description"),
            # Optional, matching the REST surface and FR-030: a file whose
            # whole content is its title and description is a legitimate
            # thing to write, and rejecting it would be a rule only one of
            # the two write surfaces had.
            body=_text(args.get("body")),
            directory=directory or None,
            relpath=relpath or None,
            actor=agent or _ANONYMOUS_ACTOR,
            agent=agent,
        )
        return {**_file_payload(written), "status": "replaced" if relpath else "created"}

    async def delete(args: dict[str, Any]) -> dict[str, Any]:
        path = _required(args, "path")
        agent = _agent(args)
        await svc.delete(path, actor=agent or _ANONYMOUS_ACTOR, agent=agent)
        return {"deleted": True, "path": path}

    registry.register(
        BuiltinTool(
            name="list",
            description=(
                "Browse Coffer's knowledge catalogue, one level at a time. With "
                "no arguments it names every collection you may read, with the "
                "collection's description and how many files it holds. Pass a "
                "path to see that directory's immediate subdirectories and "
                "files; each file comes back with a title and a one-line "
                "description, which is what you choose from — read the "
                "descriptions, pick the file that answers your question, then "
                "coffer__read it. Walk down a level at a time rather than "
                "guessing a deep path. The catalogue is generated from the "
                "directory itself, so it always matches what is on disk."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Directory to list, relative to the knowledge root "
                            "(e.g. 'shopee' or 'shopee/account'). Omit for the "
                            "list of collections."
                        ),
                    },
                    "agent": AGENT_PROPERTY,
                },
            },
            handler=list_knowledge,
        )
    )
    registry.register(
        BuiltinTool(
            name="grep",
            description=(
                "Search the text of every knowledge file you may read, literally "
                "or by regular expression, returning each matching line with its "
                "file and line number. Use it to find which line mentions an "
                "identifier, a path, or a CJK phrase — it matches bytes, so "
                "nothing is stemmed or tokenized away. Matching is exact, not "
                "conceptual: to find knowledge by topic, browse coffer__list "
                "first and grep once you know where to look. Narrow with "
                "'collection' when you already know which one holds it."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Literal text or regex."},
                    "collection": {
                        "type": "string",
                        "description": (
                            "Restrict to one collection. Omit to search every "
                            "collection you may read."
                        ),
                    },
                    "max_matches": {
                        "type": "integer",
                        "default": DEFAULT_MAX_MATCHES,
                        "minimum": 1,
                        "maximum": _MAX_MATCHES,
                    },
                    "agent": AGENT_PROPERTY,
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
                "Read one knowledge file in full by its path — the whole "
                "Markdown, not a snippet. Paths come from coffer__list and from "
                "coffer__grep matches. The response also carries the file's "
                "absolute path, so you can point the user at it."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "File path relative to the knowledge root, e.g. "
                            "'shopee/account/gateway.md'."
                        ),
                    },
                    "agent": AGENT_PROPERTY,
                },
                "required": ["path"],
            },
            handler=read,
        )
    )
    registry.register(
        BuiltinTool(
            name="write",
            description=(
                "Write a knowledge file. Pass 'directory' to create a new file "
                "in that collection or folder — the file name is derived from "
                "the title — or 'path' to replace an existing file in place. "
                "Exactly one of the two. Write down what would otherwise have "
                "to be rediscovered; the user reads these files in their own "
                "editor, so write for a human."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Human-readable title; also the file name.",
                    },
                    "description": {
                        "type": "string",
                        "description": (
                            "One line saying what this file answers. Required: "
                            "it is what the file shows in the catalogue, and "
                            "therefore what makes it findable at all."
                        ),
                    },
                    "body": {"type": "string", "description": "The Markdown content."},
                    "directory": {
                        "type": "string",
                        "description": (
                            "Collection or folder to create the file in, e.g. "
                            "'shopee' or 'shopee/account'."
                        ),
                    },
                    "path": {
                        "type": "string",
                        "description": "Existing file to replace, instead of 'directory'.",
                    },
                    "agent": AGENT_PROPERTY,
                },
                "required": ["title", "description"],
            },
            handler=write,
        )
    )
    registry.register(
        BuiltinTool(
            name="delete",
            description=(
                "Delete one knowledge file by its path. The file is removed from "
                "disk; prefer replacing it with coffer__write when the knowledge "
                "is merely out of date."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to the knowledge root.",
                    },
                    "agent": AGENT_PROPERTY,
                },
                "required": ["path"],
            },
            handler=delete,
        )
    )
