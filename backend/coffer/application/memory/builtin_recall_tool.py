"""The recall tool — memory's L2 layer, registered apart like search's own
(spec memory FR-052, FR-060).

Mirrors ``coffer.application.knowledge.builtin_search_tool`` deliberately:
``coffer__recall`` is the same shape of thing ``coffer__search`` is — a
single optional tool wired against its own service rather than the five (six,
with search) file operations knowledge's ``builtin_tools`` module groups —
and FR-060 asks for exactly one new tool here, so there is no sibling module
to fold it into. A composition root that has not wired the memory layer
simply never advertises it; one that has wired it but has no internal
connection configured still advertises it, because recall never errors for
want of one (FR-052's literal fallback).
"""

from __future__ import annotations

from typing import Any

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.memory.recall import RecallService

#: Duplicated rather than imported, matching ``builtin_search_tool``'s own
#: choice: keeps the memory and knowledge kinds' tool modules from importing
#: each other over one shared constant.
_AGENT_PROPERTY = {
    "type": "string",
    "description": "Calling agent's identity (session-injected; omit it).",
}

_DESCRIPTION = (
    "Ask Coffer's memory layer something in your own words and get back the "
    "facts that bear on it, each with where it came from — reaching past "
    "the few-hundred-token digest a session opens with. Reach for it when "
    "you need something the opening context did not include, or cannot "
    "name precisely enough to look for by keyword. It always answers: with "
    "no embedding model available it falls back to literal matching and "
    "says so in 'mode'."
)


def register_recall_tool(registry: BuiltinToolRegistry, *, recall_service: RecallService) -> None:
    """Advertise ``coffer__recall`` against ``recall_service``."""

    async def recall(args: dict[str, Any]) -> dict[str, Any]:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("'query' must be a non-empty string")
        agent = args.get("agent")
        outcome = await recall_service.recall(
            query.strip(),
            agent=agent.strip() if isinstance(agent, str) and agent.strip() else None,
        )
        return {
            "mode": outcome.mode,
            "reason": outcome.reason,
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
                    "score": fact.score,
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
                        "description": "What you need to know, in your own words.",
                    },
                    "agent": _AGENT_PROPERTY,
                },
                "required": ["query"],
            },
            handler=recall,
        )
    )
