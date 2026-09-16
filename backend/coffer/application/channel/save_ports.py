"""Ports for `/save` (spec channels FR-014) — split out of ``ports.py`` purely
for the file-size budget (that file already sat at the limit); these two
Protocols are otherwise exactly the kind of seam the rest of that module
defines, and follow its same shape.
"""

from __future__ import annotations

from typing import Any, Protocol


class CollectionCatalogPort(Protocol):
    """The collections a `/save` may confirm against (spec channels FR-014),
    reached through this seam rather than an import — the channel kind may not
    reach into the knowledge kind (import-linter contract 5f). Satisfied
    structurally by ``KnowledgeService.visible_collections``."""

    async def visible_collections(self, agent: str | None) -> list[str]: ...


class IngestPort(Protocol):
    """Saves one already-downloaded chat attachment into a knowledge
    collection (spec knowledge FR-022/FR-038), satisfied structurally by
    ``IngestService.ingest`` (same kind-isolation reason as above). The return
    value is duck-typed ``Any`` — only ``.title``/``.path`` are read."""

    async def ingest(
        self,
        *,
        collection: str,
        filename: str,
        data: bytes,
        directory: str | None = None,
        actor: str,
        agent: str | None = None,
    ) -> Any: ...


__all__ = ["CollectionCatalogPort", "IngestPort"]
