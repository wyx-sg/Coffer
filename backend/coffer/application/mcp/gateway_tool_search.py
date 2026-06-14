"""``coffer__search_tools`` — gateway tool-retrieval meta-tool (pure logic).

Special among Coffer's built-in tools: its data source is the gateway's own live
aggregation of upstream tools, which the shared ``BuiltinToolRegistry`` cannot
capture — so the gateway routes it here. Ranking is delegated to the pure domain
ranker; this module only validates args and shapes the MCP payload. The
invocation-logging + result-wrapping live in ``gateway_builtin`` (DRY).
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from typing import Any

from coffer.application.builtin_tools import COFFER_TOOL_PREFIX
from coffer.domain.mcp.tool_search import ScoredTool, rank_by_similarity, rank_tools

_logger = logging.getLogger(__name__)

TOOL_SEARCH_NAME = f"{COFFER_TOOL_PREFIX}search_tools"

# A tool's embedding is stable for a given (name + description), so cache it
# across searches: only the query is embedded each call (the upstream catalogue
# is small and changes rarely). Keyed by a hash of the embedded text.
_EMBED_CACHE: dict[str, list[float]] = {}

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


def _clamp_top_k(raw: Any) -> int:
    try:
        value = int(raw) if raw is not None else _DEFAULT_TOP_K
    except (TypeError, ValueError) as exc:
        raise ValueError("'top_k' must be an integer") from exc
    return max(1, min(_MAX_TOP_K, value))


async def execute_tool_search(
    args: dict[str, Any],
    aggregated_tools: list[dict[str, Any]],
    embedder: Any | None = None,
) -> dict[str, Any]:
    """Rank ``aggregated_tools`` against ``args['query']``; return the top-k.

    Coffer's own ``coffer__`` built-ins are excluded so search only surfaces
    upstream capabilities (the overload source). When an ``embedder`` is
    configured, ranking is semantic (cosine over embeddings); otherwise — or if
    embedding fails — it falls back to the deterministic BM25 ranker (ADR-024).
    """
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("'query' must be a non-empty string")
    top_k = _clamp_top_k(args.get("top_k"))

    candidates = [
        t for t in aggregated_tools if not str(t.get("name", "")).startswith(COFFER_TOOL_PREFIX)
    ]
    catalogue = [(str(t.get("name", "")), str(t.get("description", ""))) for t in candidates]

    ranked = await _rank(query, catalogue, top_k, embedder)

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


async def _rank(
    query: str,
    catalogue: list[tuple[str, str]],
    top_k: int,
    embedder: Any | None,
) -> list[ScoredTool]:
    """Semantic ranking when an embedder is configured; BM25 otherwise.

    Any embedding failure (engine unavailable, empty vectors, …) degrades to the
    BM25 ranker so search_tools never hard-fails on an embedder problem.
    """
    if embedder is None:
        return rank_tools(query, catalogue, top_k)
    try:
        ranked = await _semantic_rank(query, catalogue, top_k, embedder)
    except Exception:
        _logger.warning("search_tools semantic ranking failed; falling back to BM25", exc_info=True)
        return rank_tools(query, catalogue, top_k)
    return ranked if ranked else rank_tools(query, catalogue, top_k)


async def _semantic_rank(
    query: str,
    catalogue: list[tuple[str, str]],
    top_k: int,
    embedder: Any,
) -> list[ScoredTool]:
    doc_texts = [f"{name}: {description}" for name, description in catalogue]
    doc_vecs = await _embed_cached(doc_texts, embedder)
    query_vecs = await embedder.embed([query])
    if not query_vecs:
        return []
    return rank_by_similarity(query_vecs[0], doc_vecs, top_k)


async def _embed_cached(texts: Sequence[str], embedder: Any) -> list[list[float]]:
    """Embed ``texts``, reusing cached vectors and batching the misses."""
    missing = [t for t in texts if _cache_key(t) not in _EMBED_CACHE]
    if missing:
        vectors = await embedder.embed(missing)
        for text, vector in zip(missing, vectors, strict=False):
            _EMBED_CACHE[_cache_key(text)] = list(vector)
    return [_EMBED_CACHE[_cache_key(t)] for t in texts]


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = ["TOOL_SEARCH_NAME", "execute_tool_search", "tool_search_descriptor"]
