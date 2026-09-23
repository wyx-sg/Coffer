"""Ports for `/save` (spec knowledge "Ingest documents sent to a channel") — split out
of ``ports.py`` purely for the file-size budget (that file already sat at the limit);
these two Protocols are otherwise exactly the kind of seam the rest of that module
defines, and follow its same shape.
"""

from __future__ import annotations

from typing import Any, Protocol


class CollectionCatalogPort(Protocol):
    """The collections a `/save` may confirm against (spec knowledge "Ingest documents
    sent to a channel"), reached through this seam rather than an import — the channel
    kind may not reach into the knowledge kind (import-linter contract 5f). Satisfied
    structurally by ``KnowledgeService.enabled_collections``.

    It takes no agent: a collection carries no per-agent reach, so the answer
    is the same whichever agent a thread happens to be routed to."""

    async def enabled_collections(self) -> list[str]: ...


class IngestPort(Protocol):
    """Saves one already-downloaded chat attachment into a knowledge
    collection (spec knowledge "Convert uploads into material without keeping them", "Ingest
    documents sent to a channel"), satisfied structurally by
    ``IngestService.ingest`` (same kind-isolation reason as above). The return
    value is duck-typed ``Any`` — only ``.title``/``.path`` are read, and
    ``.path`` is empty while the document waits to be merged."""

    async def ingest(
        self,
        *,
        collection: str,
        filename: str,
        data: bytes,
        actor: str,
    ) -> Any: ...


__all__ = ["CollectionCatalogPort", "IngestPort"]
