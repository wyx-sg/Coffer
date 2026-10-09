"""File loose documents into ``pages/`` (spec knowledge "Sweep the knowledge
root on its mechanical duties").

A Markdown document in a collection outside ``pages/`` and ``sources/`` is a
page in the wrong place: a collection from before the two folders existed, or
an agent that wrote where the guide did not say. The sweep moves every such
document untouched for a minute, all of a tick's moves as one commit by the
``daemon`` writer with the ``layout`` operation, so a person can see and undo
it like any other change.
"""

from __future__ import annotations

import asyncio
import logging

from coffer.application.knowledge.recording import recording
from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.vault.writers import OP_LAYOUT, WRITER_DAEMON, CommitMeta
from coffer.infrastructure.knowledge import layout

logger = logging.getLogger(__name__)


async def file_loose_documents(service: KnowledgeService) -> list[str]:
    """Move every collection's loose documents into its ``pages/``; returns the
    new knowledge-root-relative paths. Never raises for one bad file."""
    moved: list[str] = []
    for row in await service.collection_rows():
        loose = await asyncio.to_thread(layout.loose_documents, row.name)
        if not loose:
            continue
        meta = CommitMeta(
            WRITER_DAEMON,
            OP_LAYOUT,
            f"File {len(loose)} loose document{'s' if len(loose) != 1 else ''} into pages/",
            collection=row.name,
        )
        async with recording(service.history, meta) as tx:
            for relpath in loose:
                try:
                    target = await asyncio.to_thread(layout.file_into_pages, relpath)
                except OSError:
                    logger.warning(
                        "knowledge.layout.move_failed", extra={"file": relpath}, exc_info=True
                    )
                    continue
                tx.touch(relpath)
                tx.touch(target)
                moved.append(target)
        service.announce(row.uid)
    if moved:
        await service.catalogue_changed()
    return moved


__all__ = ["file_loose_documents"]
