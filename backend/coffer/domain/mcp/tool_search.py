"""Pure keyword ranking over MCP tool descriptors for ``coffer__search_tools``.

No I/O, no infra import, kind-agnostic (importlinter Contracts 2b/5/6). Given a
query and a catalogue of ``(name, description)`` tools, returns the indices of
the best matches ranked by a BM25-lite score with tool-name tokens weighted
above description tokens. Deterministic — equal scores keep catalogue order — so
the retrieval eval can score it offline.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NAME_WEIGHT = 3.0
_DESC_WEIGHT = 1.0
_K1 = 1.5
_B = 0.75


def _tokenize(text: str) -> list[str]:
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return _TOKEN_RE.findall(spaced.lower())


@dataclass(frozen=True)
class ScoredTool:
    index: int
    score: float


def rank_tools(
    query: str,
    catalogue: Sequence[tuple[str, str]],
    top_k: int,
) -> list[ScoredTool]:
    """Rank ``catalogue`` against ``query``; return up to ``top_k`` best-first.

    Zero-score tools are dropped. Deterministic: ties keep catalogue order.
    """
    if top_k <= 0 or not catalogue:
        return []
    query_terms = set(_tokenize(query))
    if not query_terms:
        return []

    doc_tfs: list[dict[str, float]] = []
    doc_lens: list[float] = []
    for name, description in catalogue:
        tf: dict[str, float] = {}
        for tok in _tokenize(name):
            tf[tok] = tf.get(tok, 0.0) + _NAME_WEIGHT
        for tok in _tokenize(description):
            tf[tok] = tf.get(tok, 0.0) + _DESC_WEIGHT
        doc_tfs.append(tf)
        doc_lens.append(sum(tf.values()))

    n = len(catalogue)
    avg_len = (sum(doc_lens) / n) if n else 0.0

    idf: dict[str, float] = {}
    for term in query_terms:
        df = sum(1 for tf in doc_tfs if term in tf)
        idf[term] = math.log(1 + (n - df + 0.5) / (df + 0.5))

    scored: list[ScoredTool] = []
    for i, tf in enumerate(doc_tfs):
        score = 0.0
        for term in query_terms:
            f = tf.get(term, 0.0)
            if f == 0.0:
                continue
            norm = (doc_lens[i] / avg_len) if avg_len else 0.0
            denom = f + _K1 * (1 - _B + _B * norm)
            score += idf[term] * (f * (_K1 + 1)) / denom
        if score > 0.0:
            scored.append(ScoredTool(index=i, score=score))

    scored.sort(key=lambda s: (-s.score, s.index))
    return scored[:top_k]


def rank_by_similarity(
    query_vec: Sequence[float],
    doc_vecs: Sequence[Sequence[float]],
    top_k: int,
) -> list[ScoredTool]:
    """Rank ``doc_vecs`` by cosine similarity to ``query_vec``; best-first.

    Pure + deterministic (ties keep catalogue order). A zero-norm query or doc
    vector scores 0. Used for semantic tool search when an embedder is
    configured; the BM25 :func:`rank_tools` is the offline-eval-guarded
    fallback.
    """
    if top_k <= 0 or not doc_vecs or not query_vec:
        return []
    q_norm = math.sqrt(sum(x * x for x in query_vec))
    if q_norm == 0.0:
        return []

    scored: list[ScoredTool] = []
    for i, dv in enumerate(doc_vecs):
        d_norm = math.sqrt(sum(x * x for x in dv))
        if d_norm == 0.0:
            continue
        dot = sum(a * b for a, b in zip(query_vec, dv, strict=False))
        scored.append(ScoredTool(index=i, score=dot / (q_norm * d_norm)))

    scored.sort(key=lambda s: (-s.score, s.index))
    return scored[:top_k]


__all__ = ["ScoredTool", "rank_by_similarity", "rank_tools"]
