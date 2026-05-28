"""In-memory fake of the KnowledgeBaseStore port. Real SQLite is used for the
kb_documents table elsewhere; this fake replaces the engine layer only."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.domain.knowledge_base.document import Document
from coffer.domain.knowledge_base.store import KnowledgeBaseStore, Passage


@dataclass
class _Chunk:
    document_id: str
    filename: str
    text: str


@dataclass
class _KB:
    config: KnowledgeBaseConfig
    chunks_by_doc: dict[str, list[_Chunk]] = field(default_factory=dict)


class FakeKnowledgeBaseStore(KnowledgeBaseStore):
    """Naive in-memory KB engine for tests."""

    def __init__(self) -> None:
        self._kbs: dict[str, _KB] = {}
        self.ingest_calls = 0
        self.delete_calls = 0
        self.drop_calls = 0

    async def open(self, kb_name: str, config: KnowledgeBaseConfig) -> None:
        if kb_name not in self._kbs:
            self._kbs[kb_name] = _KB(config=config)

    async def ingest(self, kb_name: str, document: Document, text: str) -> int:
        cfg = self._kbs[kb_name].config if kb_name in self._kbs else KnowledgeBaseConfig()
        await self.open(kb_name, cfg)
        self.ingest_calls += 1
        # Naive: 1 chunk per 200 chars.
        chunks = [
            _Chunk(
                document_id=document.id,
                filename=document.filename,
                text=text[i : i + 200],
            )
            for i in range(0, max(1, len(text)), 200)
        ]
        self._kbs[kb_name].chunks_by_doc[document.id] = chunks
        return len(chunks)

    async def delete_document(self, kb_name: str, document_id: str) -> None:
        self.delete_calls += 1
        if kb_name in self._kbs:
            self._kbs[kb_name].chunks_by_doc.pop(document_id, None)

    async def search(self, kb_name: str, query: str, top_k: int) -> Sequence[Passage]:
        kb = self._kbs.get(kb_name)
        if kb is None:
            return []
        # Naive matching: lowercase substring score.
        hits: list[Passage] = []
        ql = query.lower()
        for doc_id, chunks in kb.chunks_by_doc.items():
            for pos, ch in enumerate(chunks):
                score = ch.text.lower().count(ql) / max(1, len(ch.text))
                if score > 0:
                    hits.append(
                        Passage(
                            document_id=doc_id,
                            filename=ch.filename,
                            text=ch.text,
                            score=score,
                            position=pos,
                        )
                    )
        hits.sort(key=lambda p: p.score, reverse=True)
        return hits[:top_k]

    async def drop(self, kb_name: str) -> None:
        self.drop_calls += 1
        self._kbs.pop(kb_name, None)

    async def close(self) -> None:
        self._kbs.clear()
