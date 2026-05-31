"""Keyword (no-embedding) adapter for the `KnowledgeBaseStore` port.

Plain text search over ingested documents — no embedding model, no model
download, no LlamaIndex. A KB in ``search_mode="keyword"`` is usable the
moment it is created: ingest stores the extracted text on disk (one JSON per
document under ``~/.coffer/kb/<name>/text/``) and search scans those files for
the query terms, like grepping over files.

Ranking is deliberately simple — term-frequency over passages (paragraphs).
It is not BM25; the goal is "find the files that mention this", not relevance
tuning. For meaning-based retrieval a KB opts into ``search_mode="semantic"``
(see ``llamaindex_store.py``).
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from collections.abc import Callable, Sequence
from pathlib import Path

from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.domain.knowledge_base.document import Document
from coffer.domain.knowledge_base.store import KnowledgeBaseStore, Passage

# Passages longer than this are hard-split so a single huge paragraph does not
# dominate one result row.
_MAX_PASSAGE_CHARS = 1200


def _chunk(text: str) -> list[str]:
    """Split text into passages on blank lines, hard-splitting long ones."""
    chunks: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= _MAX_PASSAGE_CHARS:
            chunks.append(para)
        else:
            for i in range(0, len(para), _MAX_PASSAGE_CHARS):
                chunks.append(para[i : i + _MAX_PASSAGE_CHARS])
    if not chunks and text.strip():
        chunks.append(text.strip())
    return chunks


def _tokenize(query: str) -> list[str]:
    """Lower-cased word tokens of the query (drops punctuation/whitespace)."""
    return [tok for tok in re.findall(r"\w+", query.lower()) if tok]


def _score(passage: str, terms: Sequence[str]) -> int:
    low = passage.lower()
    return sum(low.count(term) for term in terms)


class KeywordKnowledgeBaseStore(KnowledgeBaseStore):
    """Stores extracted text per document and ranks passages by term frequency."""

    def __init__(self, text_dir: Callable[[str], Path]) -> None:
        # ``text_dir(kb_name)`` -> the per-KB directory of ``<doc_id>.json`` files.
        self._text_dir = text_dir

    async def open(self, kb_name: str, config: KnowledgeBaseConfig) -> None:
        await asyncio.to_thread(self._text_dir(kb_name).mkdir, parents=True, exist_ok=True)

    async def ingest(self, kb_name: str, document: Document, text: str) -> int:
        def _write() -> int:
            d = self._text_dir(kb_name)
            d.mkdir(parents=True, exist_ok=True)
            record = {"filename": document.filename, "text": text}
            (d / f"{document.id}.json").write_text(
                json.dumps(record, ensure_ascii=False), encoding="utf-8"
            )
            return len(_chunk(text))

        return await asyncio.to_thread(_write)

    async def delete_document(self, kb_name: str, document_id: str) -> None:
        def _rm() -> None:
            (self._text_dir(kb_name) / f"{document_id}.json").unlink(missing_ok=True)

        await asyncio.to_thread(_rm)

    async def search(self, kb_name: str, query: str, top_k: int) -> Sequence[Passage]:
        terms = _tokenize(query)
        if not terms:
            return []

        def _scan() -> list[Passage]:
            d = self._text_dir(kb_name)
            if not d.exists():
                return []
            hits: list[Passage] = []
            for path in sorted(d.glob("*.json")):
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                filename = str(record.get("filename") or "")
                text = str(record.get("text") or "")
                for position, passage in enumerate(_chunk(text)):
                    score = _score(passage, terms)
                    if score > 0:
                        hits.append(
                            Passage(
                                document_id=path.stem,
                                filename=filename,
                                text=passage,
                                score=float(score),
                                position=position,
                            )
                        )
            hits.sort(key=lambda p: (-p.score, p.document_id, p.position))
            return hits[:top_k]

        return await asyncio.to_thread(_scan)

    async def drop(self, kb_name: str) -> None:
        def _rm() -> None:
            d = self._text_dir(kb_name)
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)

        await asyncio.to_thread(_rm)

    async def close(self) -> None:
        # No cached state to dispose; text lives on disk.
        return None
