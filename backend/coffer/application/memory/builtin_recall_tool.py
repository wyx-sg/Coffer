"""The recall tool — memory's L2 layer, registered apart like search's own
(spec memory FR-023, FR-027).

Mirrors ``coffer.application.knowledge.builtin_search_tool`` deliberately:
``coffer__recall`` is the same shape of thing ``coffer__search`` is — a
single optional tool wired against its own service rather than the five (six,
with search) file operations knowledge's ``builtin_tools`` module groups —
and FR-027 asks for exactly one new tool here, so there is no sibling module
to fold it into. A composition root that has not wired the memory layer
simply never advertises it; one that has needs nothing else configured,
because recall is a literal scan over facts already on disk (FR-023).
"""

from __future__ import annotations

from typing import Any

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.memory.recall import RecallService

_DESCRIPTION = (
    "Look up facts in Coffer's memory layer by a word or phrase, and get "
    "each one whole with where it came from — reaching past the "
    "few-hundred-token digest a session opens with. Reach for it when you "
    "need something the opening context did not include. Matching is "
    "literal and case-insensitive, over each fact's summary and body, so "
    "give it a distinctive word or phrase rather than a whole question."
)


def register_recall_tool(registry: BuiltinToolRegistry, *, recall_service: RecallService) -> None:
    """Advertise ``coffer__recall`` against ``recall_service``."""

    async def recall(args: dict[str, Any]) -> dict[str, Any]:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("'query' must be a non-empty string")
        # Written by the gateway from the session handshake, never by the
        # caller — it is not in the schema below on purpose.
        agent = args.get("agent")
        outcome = await recall_service.recall(
            query.strip(),
            agent=agent.strip() if isinstance(agent, str) and agent.strip() else None,
        )
        return {
            "facts": [
                {
                    "path": fact.path,
                    "title": fact.title,
                    "description": fact.description,
                    "body": fact.body,
                    "type": fact.type,
                    "partition": fact.partition,
                    "origins": [
                        {"agent": agent_name, "native_path": native_path}
                        for agent_name, native_path in fact.origins
                    ],
                }
                for fact in outcome.facts
            ],
        }

    registry.register(
        BuiltinTool(
            name="recall",
            description=_DESCRIPTION,
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "The word or phrase to look for. Matched literally, case-insensitively."
                        ),
                    },
                },
                "required": ["query"],
            },
            handler=recall,
        )
    )
