"""The ranked-retrieval tool, registered apart from its five siblings.

``coffer__search`` is the one knowledge tool not backed by ``KnowledgeService``
and the one that is optional: an installation with no ranked retrieval wired
simply never advertises it, rather than advertising a tool that raises. Both of
those make it a poor fit inside ``builtin_tools``, whose whole job is the five
file operations over one service — so it lives here, and that module calls in.
"""

from __future__ import annotations

from typing import Any

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.knowledge.search import SearchService

#: Duplicated rather than imported to keep the import one-way: the sibling
#: module calls into this one, never the reverse.
_AGENT_PROPERTY = {
    "type": "string",
    "description": "Calling agent's identity (session-injected; omit it).",
}

_DESCRIPTION = (
    "Find the knowledge files that MEAN what you describe, ranked, each with "
    "the lines that matched. Reach for it when you cannot afford to browse "
    "coffer__list first, or when you have no exact words to grep for — ask in "
    "your own words, as a question or a description of the problem. It always "
    "answers: with no embedding model available it falls back to a literal "
    "search and says so in 'mode'. For an identifier or an exact phrase, "
    "coffer__grep is still the better tool."
)


def register_search_tool(registry: BuiltinToolRegistry, *, search_service: SearchService) -> None:
    """Advertise ``coffer__search`` against ``search_service``."""

    async def search(args: dict[str, Any]) -> dict[str, Any]:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("'query' must be a non-empty string")
        agent = args.get("agent")
        collection = args.get("collection")
        outcome = await search_service.search(
            query.strip(),
            agent=agent.strip() if isinstance(agent, str) and agent.strip() else None,
            collection=(
                collection.strip() if isinstance(collection, str) and collection.strip() else None
            ),
        )
        return {
            "mode": outcome.mode,
            "reason": outcome.reason,
            "results": [
                {
                    "path": hit.path,
                    "title": hit.title,
                    "description": hit.description,
                    "score": hit.score,
                    "heading": hit.heading,
                    "lines": [
                        {"line_number": number, "line": line} for number, line in hit.excerpt
                    ],
                }
                for hit in outcome.hits
            ],
        }

    registry.register(
        BuiltinTool(
            name="search",
            description=_DESCRIPTION,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "What you are looking for, in your own words.",
                    },
                    "collection": {
                        "type": "string",
                        "description": (
                            "Restrict to one collection. Omit to search every "
                            "collection you may read."
                        ),
                    },
                    "agent": _AGENT_PROPERTY,
                },
                "required": ["query"],
            },
            handler=search,
        )
    )
