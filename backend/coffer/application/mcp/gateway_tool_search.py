"""``coffer__search_tools`` — gateway tool-retrieval meta-tool (pure logic).

Special among Coffer's built-in tools: its data source is the gateway's own live
aggregation of upstream tools, which the shared ``BuiltinToolRegistry`` cannot
capture — so the gateway routes it here. Ranking is delegated to the pure domain
ranker; this module only validates args and shapes the MCP payload. The
invocation-logging + result-wrapping live in ``gateway_builtin`` (DRY).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from coffer.application.builtin_tools import COFFER_TOOL_PREFIX
from coffer.domain.mcp.tool_search import rank_tools, schema_text
from coffer.domain.mcp.tool_tiering import split_prefixed

TOOL_SEARCH_NAME = f"{COFFER_TOOL_PREFIX}search_tools"

_DEFAULT_TOP_K = 5
_MAX_TOP_K = 20

_DESCRIPTION = (
    "Search Coffer's aggregated catalogue of upstream MCP tools by intent and "
    "return the most relevant tool definitions (name, description, inputSchema). "
    "Use this FIRST when you need a capability but don't know which tool provides "
    "it, instead of scanning the full tool list; then call the returned tool "
    "directly."
)

_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "What you want to do, in natural language or keywords.",
        },
        "top_k": {
            "type": "integer",
            "default": _DEFAULT_TOP_K,
            "minimum": 1,
            "maximum": _MAX_TOP_K,
        },
    },
    "required": ["query"],
}


def tool_search_descriptor() -> dict[str, Any]:
    """The ``tools/list`` entry for ``coffer__search_tools``."""
    return {"name": TOOL_SEARCH_NAME, "description": _DESCRIPTION, "inputSchema": _INPUT_SCHEMA}


def _search_corpus(
    tools: list[dict[str, Any]], about: Mapping[str, str] | None = None
) -> list[tuple[str, str, str]]:
    """Build the (name_text, description, parameters) triples the ranker scores.

    The listed name is doubly namespaced — ``jira__jira_get_issue`` tokenizes as
    jira, jira, get, issue — so the server token lands twice at the ranker's
    name weight, inflating the document length and crowding out the tokens that
    actually carry the intent. Splitting the namespace off collapses it to one.

    A custom-tool group's description (``about``, keyed by group name) joins the
    description text of each of its tools (spec mcp-gateway "Describe a
    custom-tool group").

    The input schema's parameter names, descriptions and enum values are the
    third, lightest-weighted text: an intent like "find a user by phone" often
    lives only in a parameter such as ``phone_list``.
    """
    corpus: list[tuple[str, str, str]] = []
    for tool in tools:
        server, bare = split_prefixed(str(tool.get("name", "")))
        text = f"{server} {bare}" if server else bare
        description = str(tool.get("description", ""))
        group = (about or {}).get(server) if server else None
        parameters = schema_text(tool.get("inputSchema"))
        corpus.append((text, f"{description}\n{group}" if group else description, parameters))
    return corpus


def _result_entry(tool: dict[str, Any], score: float, about: Mapping[str, str]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": tool.get("name", ""),
        "description": tool.get("description", ""),
        "inputSchema": tool.get("inputSchema", {}),
        "score": round(score, 4),
    }
    # Each result carries the real upstream definition, schema of the result included.
    if tool.get("outputSchema"):
        entry["outputSchema"] = tool["outputSchema"]
    server, _ = split_prefixed(str(entry["name"]))
    if server and server in about:
        entry["group_description"] = about[server]
    return entry


def _clamp_top_k(raw: Any) -> int:
    try:
        value = int(raw) if raw is not None else _DEFAULT_TOP_K
    except (TypeError, ValueError) as exc:
        raise ValueError("'top_k' must be an integer") from exc
    return max(1, min(_MAX_TOP_K, value))


async def execute_tool_search(
    args: dict[str, Any],
    aggregated_tools: list[dict[str, Any]],
    exposure: Mapping[str, str] | None = None,
    about: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Rank ``aggregated_tools`` against ``args['query']``; return the top-k.

    Coffer's own ``coffer__`` built-ins are excluded so search only surfaces
    upstream capabilities (the overload source). Ranking is the deterministic
    BM25 ranker (ADR tool-overload-tier-the-list-search-the-rest); the alternative
    cosine-over-embeddings path was removed with every other use of embeddings
    in Coffer, and was never wired to a real embedder in any case.

    ``exposure`` is the person's per-tool override: among equally scored tools,
    one set to ``search`` (reachable only here) goes ahead of one pinned
    ``listed``, which the agent already sees. Every tool stays searchable.

    ``about`` maps a custom-tool group to its description: scored with the
    group's tools, and returned beside each as ``group_description``.
    """
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("'query' must be a non-empty string")
    top_k = _clamp_top_k(args.get("top_k"))

    candidates = [
        t for t in aggregated_tools if not str(t.get("name", "")).startswith(COFFER_TOOL_PREFIX)
    ]
    groups = about or {}
    catalogue = _search_corpus(candidates, groups)

    overrides = exposure or {}
    prefer = [overrides.get(str(t.get("name", ""))) == "search" for t in candidates]
    ranked = rank_tools(query, catalogue, top_k, prefer=prefer)

    tools = [_result_entry(candidates[s.index], s.score, groups) for s in ranked]
    return {"tools": tools, "total_searched": len(candidates)}


__all__ = [
    "TOOL_SEARCH_NAME",
    "execute_tool_search",
    "tool_search_descriptor",
]
