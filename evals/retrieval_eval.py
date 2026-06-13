"""Retrieval eval — measures Coffer's real keyword (FTS5) retrieval.

Builds a throwaway SQLite substrate (the same one the integration tests use),
ingests a small fixture corpus, then runs the golden queries through Coffer's
``SqliteKnowledgeIndex.keyword_search`` and scores recall@k / MRR.

Keyword mode needs no embedding model, so this is fully local, deterministic,
and free — it runs anywhere Coffer's backend imports. The vector path (local
``fastembed`` embeddings) is a documented extension that needs a Python 3.12
environment with onnxruntime wheels; see evals/README.md.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import coffer.infrastructure.knowledge  # noqa: F401 — registers ORM + FTS5 DDL
from coffer.domain.knowledge.document import (
    KIND_KNOWLEDGE_BASE,
    WORKSPACE_GLOBAL_PROJECT_ID,
    Document,
)
from coffer.infrastructure.knowledge.repository import DocumentRepo
from coffer.infrastructure.knowledge.sqlite_index import SqliteKnowledgeIndex
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)

from evals._io import load_jsonl
from evals.metrics import mrr, recall_at_k

_RESOURCE = "evalkb"


def _doc(doc_id: str, title: str) -> Document:
    now = datetime.now(UTC)
    return Document(
        id=doc_id,
        kind=KIND_KNOWLEDGE_BASE,
        resource_name=_RESOURCE,
        project_id=WORKSPACE_GLOBAL_PROJECT_ID,
        path=f"docs/{doc_id}.md",
        title=title,
        content_sha256="x",
        source_mode="converted",
        created_at=now,
        updated_at=now,
    )


async def run_retrieval_eval(*, top_k: int = 3) -> dict:
    """Run the keyword-retrieval suite; return a scorecard dict."""
    corpus = load_jsonl("corpus.jsonl")
    queries = load_jsonl("retrieval.jsonl")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "eval.db"
        engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{db_path}")
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            sm = session_maker(engine)
            repo = DocumentRepo(sm)
            index = SqliteKnowledgeIndex(
                sm, kind=KIND_KNOWLEDGE_BASE, resource_name=_RESOURCE
            )

            for doc in corpus:
                await repo.upsert_document(_doc(doc["doc_id"], doc["title"]))
                await index.upsert_chunks(doc["doc_id"], list(doc["chunks"]), None)

            cases: list[dict] = []
            for q in queries:
                expected = set(q["expected"])
                # Fetch extra passages, then roll up to distinct documents
                # (preserving rank) so recall@k / MRR are document-level.
                hits = await index.keyword_search(_RESOURCE, q["query"], top_k * 5)
                ranked = list(dict.fromkeys(h.document_id for h in hits))
                cases.append(
                    {
                        "query": q["query"],
                        "expected": sorted(expected),
                        "ranked": ranked,
                        "recall": recall_at_k(ranked, expected, k=top_k),
                        "mrr": mrr(ranked, expected),
                    }
                )
        finally:
            await engine.dispose()

    n = len(cases)
    mean_recall = sum(c["recall"] for c in cases) / n if n else 0.0
    mean_mrr = sum(c["mrr"] for c in cases) / n if n else 0.0
    return {
        "suite": "retrieval",
        "primary": {"name": f"recall@{top_k}", "value": round(mean_recall, 4)},
        "secondary": {"mrr": round(mean_mrr, 4)},
        "n": n,
        "cases": cases,
    }
