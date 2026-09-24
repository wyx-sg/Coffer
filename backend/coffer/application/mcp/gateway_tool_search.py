"""``coffer__search_tools`` — gateway tool-retrieval meta-tool (pure logic).

Special among Coffer's built-in tools: its data source is the gateway's own live
aggregation of upstream tools, which the shared ``BuiltinToolRegistry`` cannot
capture — so the gateway routes it here. Ranking is delegated to the pure domain
ranker; this module only validates args and shapes the MCP payload. The
invocation-logging + result-wrapping live in ``gateway_builtin`` (DRY).
"""

from __future__ import annotations

from typing import Any

from coffer.application.builtin_tools import COFFER_TOOL_PREFIX
from coffer.domain.mcp.tool_search import rank_tools
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


def _search_corpus(tools: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Build the (name_text, description) pairs the rankers score.

    The listed name is doubly namespaced — ``jira__jira_get_issue`` tokenizes as
    jira, jira, get, issue — so the server token lands twice at the ranker's
    name weight, inflating the document length and crowding out the tokens that
    actually carry the intent. Splitting the namespace off collapses it to one.
    """
    corpus: list[tuple[str, str]] = []
    for tool in tools:
        server, bare = split_prefixed(str(tool.get("name", "")))
        text = f"{server} {bare}" if server else bare
        corpus.append((text, str(tool.get("description", ""))))
    return corpus


def _clamp_top_k(raw: Any) -> int:
    try:
        value = int(raw) if raw is not None else _DEFAULT_TOP_K
    except (TypeError, ValueError) as exc:
        raise ValueError("'top_k' must be an integer") from exc
    return max(1, min(_MAX_TOP_K, value))


async def execute_tool_search(
    args: dict[str, Any],
    aggregated_tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Rank ``aggregated_tools`` against ``args['query']``; return the top-k.

    Coffer's own ``coffer__`` built-ins are excluded so search only surfaces
    upstream capabilities (the overload source). Ranking is the deterministic
    BM25 ranker (ADR coffer-model-is-an-internal-engine); the alternative
    cosine-over-embeddings path was removed with every other use of embeddings
    in Coffer, and was never wired to a real embedder in any case.
    """
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("'query' must be a non-empty string")
    top_k = _clamp_top_k(args.get("top_k"))

    candidates = [
        t for t in aggregated_tools if not str(t.get("name", "")).startswith(COFFER_TOOL_PREFIX)
    ]
    catalogue = _search_corpus(candidates)

    ranked = rank_tools(query, catalogue, top_k)

    tools = [
        {
            "name": candidates[s.index].get("name", ""),
            "description": candidates[s.index].get("description", ""),
            "inputSchema": candidates[s.index].get("inputSchema", {}),
            "score": round(s.score, 4),
        }
        for s in ranked
    ]
    return {"tools": tools, "total_searched": len(candidates)}


__all__ = [
    "TOOL_SEARCH_NAME",
    "execute_tool_search",
    "tool_search_descriptor",
]
