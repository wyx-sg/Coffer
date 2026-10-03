"""Adopt the inbox files an agent wrote with its own file tools (spec knowledge
"Submit material by writing a file into the inbox").

An agent adds knowledge by writing ``<collection>/.inbox/<name>.md``. The sweep
runs this *before* it commits what changed on disk, so the file is committed
already normalised, and one ``knowledge_written`` event names it.

A file is recognised as written outside Coffer when git has never seen it and
no open operation owns it — every Coffer surface commits its own writes at once.
With no git, a file lacking a key a Coffer surface always writes stands in.
Only registered collections are walked, so a Markdown file under any other
top-level directory is left alone and is not catalogued, and a non-Markdown file
in an inbox is left in place and logged.
"""

from __future__ import annotations

import asyncio
import logging

from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.audit import AuditEventType
from coffer.infrastructure.knowledge import inbox

logger = logging.getLogger(__name__)


def _dropped_names(collection: str, new_paths: set[str] | None) -> list[str]:
    """Inbox items to adopt: the never-committed ones when git can say, else the
    ones lacking a key a Coffer surface always writes."""
    found = []
    for name in inbox.inbox_items(collection):
        if new_paths is not None:
            if inbox.inbox_path(collection, name) in new_paths:
                found.append(name)
        elif not inbox.has_complete_frontmatter(collection, name):
            found.append(name)
    return found


async def adopt_dropped_files(service: KnowledgeService) -> list[str]:
    """Normalise and audit every new inbox file; returns their knowledge-root-
    relative paths. Never raises for one bad file."""
    history = service.history
    new_paths = (
        set(await asyncio.to_thread(history.new_files))
        if history is not None and history.available()
        else None
    )
    adopted: list[str] = []
    for row in await service.collection_rows():
        collection = row.name
        for name in await asyncio.to_thread(inbox.non_markdown_items, collection):
            logger.info(
                "knowledge.intake.not_markdown",
                extra={"collection": collection, "file": name},
            )
        names = await asyncio.to_thread(_dropped_names, collection, new_paths)
        for name in names:
            try:
                title, actor, reported = await asyncio.to_thread(
                    inbox.adopt_dropped, collection, name
                )
            except OSError:
                logger.warning(
                    "knowledge.intake.adopt_failed",
                    extra={"collection": collection, "file": name},
                    exc_info=True,
                )
                continue
            await service.audit.record(
                AuditEventType.KNOWLEDGE_WRITTEN.value,
                resource=row,
                actor=actor,
                details={
                    "title": title,
                    "item": name,
                    "path": None,
                    "pending": True,
                    "actor_reported": reported,
                },
            )
            adopted.append(inbox.inbox_path(collection, name))
        if names:
            service.announce(row.uid)
    return adopted


__all__ = ["adopt_dropped_files"]
