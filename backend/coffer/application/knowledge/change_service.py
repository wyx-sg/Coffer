"""The knowledge changes feed, undoing a delete, and a collection's description
(spec knowledge "Follow edits across collections in one feed", "Undo a
knowledge delete from its toast", "Name a collection by its folder and edit its
description in place").

The history is the vault repository's, under ``knowledge/``
(``infrastructure.knowledge.history``); this service is what the surfaces ask.
Every read first commits what changed outside Coffer as ``disk`` writes, so
what it reports is the tree as it is, not as Coffer last wrote it. A delete's
toast finds its change in the feed and restores it; a document's versions are
read and restored through the vault's history (spec vault-storage "Show and
restore any version of a vault file or folder").

Two writes live here, and both are a person's: **restore a delete** puts back
what a delete removed, and **describe** rewrites a collection's description.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Callable

from coffer.application.audit_service import AuditService
from coffer.application.knowledge import collection_writes
from coffer.application.knowledge.recording import settle
from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.git_handoff import git_missing_details
from coffer.domain.knowledge.entry import CollectionEntry
from coffer.domain.knowledge.errors import KnowledgeHistoryUnavailable, KnowledgeNotADelete
from coffer.domain.knowledge.history import Change, ChangesPage
from coffer.domain.pagination import decode_cursor, encode_cursor
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.history import KnowledgeHistory

#: The cursor tag of the feed (spec resource-framework "Page growing lists by
#: an opaque cursor").
_FEED = "knowledge_changes"
#: How many commits one read of git asks for while filling a page.
_BATCH = 100
_INBOX_SEGMENT = f"/{paths.INBOX_DIR_NAME}/"


def _is_document(path: str) -> bool:
    return _INBOX_SEGMENT not in path


class KnowledgeChangeService:
    def __init__(
        self,
        *,
        knowledge: KnowledgeService,
        history: KnowledgeHistory | None,
        audit: AuditService,
        machine: Callable[[], str] = lambda: "this machine",
    ) -> None:
        self._knowledge = knowledge
        self._history = history
        self._audit = audit
        #: The OS and architecture, for the install-git hand-off.
        self._machine = machine

    def _require(self) -> KnowledgeHistory:
        history = self._history
        if history is not None and history.available():
            return history
        if history is None or not history.git_installed():
            raise KnowledgeHistoryUnavailable(
                "git is not installed on this machine",
                git_missing_details(self._machine(), needed_for="the knowledge history"),
            )
        raise KnowledgeHistoryUnavailable("the vault has no history repository")

    async def _settled(self) -> KnowledgeHistory:
        history = await asyncio.to_thread(self._require)
        await settle(history)
        return history

    async def restore_deleted(self, version: str, *, actor: str) -> Change:
        """Put back what a delete removed — a document, or a whole collection.
        A version that is no knowledge change is not a delete either."""
        history = await self._settled()
        change = await asyncio.to_thread(history.change, version)
        if change is None:
            raise KnowledgeNotADelete(version)
        made = await collection_writes.restore_deleted(
            self._knowledge, history, self._audit, change, actor=actor
        )
        restored = await asyncio.to_thread(history.change, made) if made else None
        if restored is None:
            raise KnowledgeNotADelete(version)
        return restored

    async def describe(self, uid: str, description: str, *, actor: str) -> CollectionEntry:
        """Rewrite a collection's description — its README's first paragraph."""
        return await collection_writes.describe_collection(
            self._knowledge, self._audit, uid, description, actor=actor
        )

    async def changes(
        self, *, collection: str | None = None, limit: int = 50, cursor: str | None = None
    ) -> ChangesPage:
        """Recent changes newest first."""
        filters = {"collection": collection}
        position = decode_cursor(cursor, list_tag=_FEED, filters=filters)
        if collection is not None:
            await self._knowledge.require_collection(collection)
        history = await self._settled()
        found = await asyncio.to_thread(
            self._fill, history, collection, str(position[0]) if position else None, limit
        )
        page = found[:limit]
        more = len(found) > limit
        return ChangesPage(
            changes=tuple(page),
            next_cursor=encode_cursor(_FEED, filters, [page[-1].version]) if more else None,
        )

    def _fill(
        self, history: KnowledgeHistory, collection: str | None, after: str | None, limit: int
    ) -> list[Change]:
        """Up to ``limit + 1`` visible changes after ``after``, in log order.

        A commit that touched only the inbox changed no document, so it is not
        listed; inbox paths are dropped from every change's documents.
        """
        start = f"{after}^" if after else None
        spec = (collection,) if collection else ()
        out: list[Change] = []
        skip = 0
        while len(out) <= limit:
            batch = history.log(*spec, start=start, limit=_BATCH, skip=skip)
            if not batch:
                break
            skip += len(batch)
            for change in batch:
                documents = tuple(
                    d
                    for d in change.documents
                    if _is_document(d.path)
                    and (collection is None or d.path.startswith(f"{collection}/"))
                )
                if documents:
                    out.append(dataclasses.replace(change, documents=documents))
        return out


__all__ = ["KnowledgeChangeService"]
