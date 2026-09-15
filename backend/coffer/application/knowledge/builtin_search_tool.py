"""The search tool, registered apart from its five siblings.

``coffer__search`` is the one knowledge tool not backed directly by
``KnowledgeService`` and the one that is optional: an installation with no
search service wired simply never advertises it, rather than advertising a tool
that raises. Both of those make it a poor fit inside ``builtin_tools``, whose
whole job is the five file operations over one service — so it lives here, and
that module calls in.
"""

from __future__ import annotations

from typing import Any

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.knowledge.search import SearchService

_DESCRIPTION = (
    "Find the knowledge FILES that contain a word or phrase, each with the "
    "lines that matched — a literal text search, one result per file, with "
    "the file's title and description so you can tell what you found. Reach "
    "for it when you want the file rather than the line, and cannot afford to "
    "browse coffer__list first. Give it a distinctive word or exact phrase, "
    "not a sentence: matching is literal (a regular expression, case "
    "sensitive), so a whole question in your own words will find nothing. "
    "When you want every matching line across the corpus instead, "
    "coffer__grep is the same matcher reported line by line."
)


def register_search_tool(registry: BuiltinToolRegistry, *, search_service: SearchService) -> None:
    """Advertise ``coffer__search`` against ``search_service``."""

    async def search(args: dict[str, Any]) -> dict[str, Any]:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("'query' must be a non-empty string")
        # Written by the gateway from the session handshake, never by the
        # caller — it is not in the schema below on purpose.
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
            "results": [
                {
                    "path": hit.path,
                    "title": hit.title,
                    "description": hit.description,
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
                        "description": (
                            "The word, phrase or regular expression to look "
                            "for. Matched literally and case-sensitively."
                        ),
                    },
                    "collection": {
                        "type": "string",
                        "description": (
                            "Restrict to one collection. Omit to search every "
                            "collection you may read."
                        ),
                    },
                },
                "required": ["query"],
            },
            handler=search,
        )
    )
