"""KnowledgeBaseStore port + Passage value object.

The port expresses what Coffer's application layer needs. Real adapters live
in infrastructure/ — this module imports neither LlamaIndex nor any other
engine.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from coffer.domain.knowledge_base.config import KnowledgeBaseConfig
from coffer.domain.knowledge_base.document import Document


@dataclass(frozen=True)
class Passage:
    """One ranked chunk returned from `KnowledgeBaseStore.search`."""

    document_id: str
    filename: str
    text: str
    score: float
    position: int


@runtime_checkable
class KnowledgeBaseStore(Protocol):
    """Port for chunk + embed + retrieve. Single point of engine coupling."""

    async def open(self, kb_name: str, config: KnowledgeBaseConfig) -> None:
        """Ensure the engine has loaded (or created) the per-KB index."""
        ...

    async def ingest(self, kb_name: str, document: Document, text: str) -> int:
        """Chunk, embed, and add `text` under `document.id`. Returns chunk count."""
        ...

    async def delete_document(self, kb_name: str, document_id: str) -> None:
        """Remove every chunk for `document_id` from the index."""
        ...

    async def search(self, kb_name: str, query: str, top_k: int) -> Sequence[Passage]:
        """Return the top_k ranked passages for `query`."""
        ...

    async def drop(self, kb_name: str) -> None:
        """Tear down the index entirely. Called from the kind's on_delete hook."""
        ...

    async def close(self) -> None:
        """Dispose any cached state. Called at daemon shutdown."""
        ...
