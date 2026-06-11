"""Unit: cross-store recall merging (reciprocal rank fusion)."""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.application.memory.recall import merge_ranked
from coffer.domain.knowledge.retrieval import MemoryHit


def _hit(hit_id: str, score: float) -> MemoryHit:
    return MemoryHit(
        id=hit_id, text=hit_id, score=score, source=f"s:{hit_id}", time=datetime.now(tz=UTC)
    )


def test_unbounded_keyword_scores_do_not_dominate_vector_hits() -> None:
    """bm25 keyword scores are unbounded; vector scores are ≤1. A raw-score
    merge would always rank every keyword hit above every vector hit — RRF
    interleaves them by per-store rank instead (review M10)."""
    keyword_store = [_hit("k1", 87.3), _hit("k2", 43.1)]
    vector_store = [_hit("v1", 0.93), _hit("v2", 0.88)]

    merged = merge_ranked([keyword_store, vector_store], top_k=4)
    ids = [h.id for h in merged]
    # Top-ranked hits of BOTH stores come first (tie on rank 0), then rank 1s.
    assert set(ids[:2]) == {"k1", "v1"}
    assert set(ids[2:]) == {"k2", "v2"}


def test_duplicate_ids_accumulate_rank_credit() -> None:
    """A fact surfacing in both stores outranks single-store hits."""
    a = [_hit("dup", 1.0), _hit("only-a", 0.9)]
    b = [_hit("dup", 50.0), _hit("only-b", 10.0)]
    merged = merge_ranked([a, b], top_k=3)
    assert merged[0].id == "dup"
    assert len(merged) == 3


def test_top_k_truncates() -> None:
    group = [[_hit(f"h{i}", 1.0) for i in range(10)]]
    assert len(merge_ranked(group, top_k=3)) == 3
