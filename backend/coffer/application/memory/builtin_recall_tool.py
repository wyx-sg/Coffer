"""The recall tool — memory's one built-in, registered apart like search's own
(spec memory "Recall locations by literal match", "Expose only coffer__recall").

Mirrors ``coffer.application.knowledge.builtin_search_tool`` deliberately:
``coffer__recall`` is the same shape of thing ``coffer__search`` is — a single
optional tool wired against its own service rather than the file operations
knowledge's ``builtin_tools`` module groups — and "Expose only coffer__recall" asks
for exactly one tool here, so there is no sibling module to fold it into. A
composition root that has not wired the memory layer simply never advertises it; one that has
needs nothing else configured, because recall is a literal scan over notes
already on disk (see "Recall locations by literal match").

The description below is doing real work, so it is worth saying what it must
convey and why. It **locates**: the answer is paths, and the caller reads the
file itself, which is the whole shape of this layer (see "Keep notes readable as plain
files"). It says where to reach for it: the session already opened with the full index
of the partition it is in, so this is for a partition it is *not* in. And it says
matching is **literal**, because the previous design's opening line asked for "a
natural-language query" against a tool that has only ever done substring matching — an
agent that obeyed sent a whole question, matched nothing, and read the empty answer as
an empty memory.
"""

from __future__ import annotations

from typing import Any

from coffer.application.builtin_tools import BuiltinTool, BuiltinToolRegistry
from coffer.application.memory.recall import RecallService

_DESCRIPTION = (
    "Locate notes in Coffer's memory — the notes distilled from what this "
    "developer's agents have learned. It answers with each note's absolute "
    "file path, title and one-line description; read the file yourself when "
    "you want the body. Your session already opened with the whole index of "
    "this project's memory, so reach for this when you need a note from "
    "another project. Matching is literal and case-insensitive, over each "
    "note's summary, body and search terms, so give it a distinctive word or "
    "phrase rather than a question."
)


def register_recall_tool(registry: BuiltinToolRegistry, *, recall_service: RecallService) -> None:
    """Advertise ``coffer__recall`` against ``recall_service``."""

    async def recall(args: dict[str, Any]) -> dict[str, Any]:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("'query' must be a non-empty string")
        # ``args`` still arrives with an ``agent`` the gateway wrote from the
        # session handshake — it does that for every builtin, generically —
        # and this tool ignores it. It used to narrow the scan to that agent's
        # per-agent scope on the partitions, which nobody had chosen: the
        # scope defaulted to whichever agents a partition was aggregated
        # from, so an agent could be refused every note about the repository
        # it was working in. Recall spans every enabled partition now.
        outcome = await recall_service.recall(query.strip())
        return {
            "notes": [
                {
                    "path": note.path,
                    "title": note.title,
                    "description": note.description,
                    "type": note.type,
                    "partition": note.partition,
                }
                for note in outcome.notes
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
