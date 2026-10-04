"""Reading a collection's history, restoring a version, and the recent-changes
feed (spec knowledge "Keep every document's history",
"Follow edits across collections in one feed").

The history is the vault repository's, under ``knowledge/``
(``infrastructure.knowledge.history``); this service is what the surfaces ask.
Every read first commits what changed outside Coffer as ``disk`` writes, so
what it reports is the tree as it is, not as Coffer last wrote it.

Two writes live here, and both are a person's: **restore** puts one version of
one document back as a new commit, and **restore a delete** puts back what a
delete removed. A commit a retired ``curation`` pass wrote stays in the history
and is restored the same way as any other.
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Callable

from coffer.application.audit_service import AuditService
from coffer.application.knowledge import collection_writes
from coffer.application.knowledge.recording import recording, settle
from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.audit import AuditEventType
from coffer.domain.git_handoff import git_missing_details
from coffer.domain.knowledge.entry import CollectionEntry, KnowledgeFile
from coffer.domain.knowledge.errors import (
    KnowledgeHistoryUnavailable,
    KnowledgeVersionNotFound,
)
from coffer.domain.knowledge.history import (
    OP_RESTORE,
    REMOVED,
    WRITER_USER,
    Change,
    ChangesPage,
    DocumentDiff,
    DocumentVersion,
)
from coffer.domain.pagination import decode_cursor, encode_cursor
from coffer.domain.vault.writers import CommitMeta
from coffer.infrastructure.knowledge import fs, paths
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.history import KnowledgeHistory

#: The cursor tag of the feed (spec resource-framework "Page growing lists by
#: an opaque cursor").
_FEED = "knowledge_changes"
#: How many commits one read of git asks for while filling a page.
_BATCH = 100
_INBOX_SEGMENT = f"/{paths.INBOX_DIR_NAME}/"


def _is_document(path: str) -> bool:
    return _INBOX_SEGMENT not in path


class KnowledgeHistoryService:
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

    async def _change(self, history: KnowledgeHistory, version: str) -> Change:
        found = await asyncio.to_thread(history.change, version)
        if found is None:
            raise KnowledgeVersionNotFound(version)
        return found

    # --- one document -------------------------------------------------------

    async def versions(self, relpath: str) -> list[DocumentVersion]:
        """A document's versions, newest first, each with its writer."""
        await self._knowledge.require_collection(relpath)
        paths.require_document(relpath)
        history = await self._settled()
        changes = await asyncio.to_thread(history.log, relpath)
        return [
            DocumentVersion(
                change=c,
                path=relpath,
                removed=any(d.path == relpath and d.status == REMOVED for d in c.documents),
            )
            for c in changes
        ]

    async def version_diff(self, relpath: str, version: str) -> DocumentDiff:
        """What ``version`` did to ``relpath``."""
        paths.require_document(relpath)
        history = await asyncio.to_thread(self._require)
        change = await self._change(history, version)
        doc = next((d for d in change.documents if d.path == relpath), None)
        if doc is None:
            raise KnowledgeVersionNotFound(version, relpath)
        text = await asyncio.to_thread(history.diff, change.version, relpath)
        return DocumentDiff(
            path=relpath, status=doc.status, diff=text, added=doc.added, removed=doc.removed
        )

    async def version_body(self, relpath: str, version: str) -> str:
        """The document's body as ``version`` left it — what Compare with
        current sets against the document as it is now."""
        paths.require_document(relpath)
        history = await asyncio.to_thread(self._require)
        change = await self._change(history, version)
        raw = await asyncio.to_thread(history.show, change.version, relpath)
        if raw is None:
            raise KnowledgeVersionNotFound(version, relpath)
        return split_frontmatter(fs.decode(raw))[1]

    async def restore(self, relpath: str, version: str, *, actor: str) -> KnowledgeFile:
        """Put ``relpath`` back as it was at ``version``, as a new commit."""
        row = await self._knowledge.require_collection(relpath)
        paths.require_document(relpath)
        history = await asyncio.to_thread(self._require)
        change = await self._change(history, version)
        raw = await asyncio.to_thread(history.show, change.version, relpath)
        if raw is None:
            raise KnowledgeVersionNotFound(version, relpath)
        meta = CommitMeta(
            WRITER_USER,
            OP_RESTORE,
            f"Restore {relpath}",
            actor=actor,
            collection=row.name,
            restored_from=change.version,
        )
        async with recording(history, meta) as tx:
            tx.touch(relpath)
            await asyncio.to_thread(fs.write_bytes, relpath, raw)
        await self._audit.record(
            AuditEventType.KNOWLEDGE_EDITED.value,
            resource=row,
            actor=actor,
            details={"path": relpath, "restored_from": change.version},
        )
        await self._knowledge.catalogue_changed()
        return await asyncio.to_thread(fs.read_file, relpath)

    async def restore_deleted(self, version: str, *, actor: str) -> Change:
        """Put back what a delete removed — a document, or a whole collection."""
        history = await self._settled()
        change = await self._change(history, version)
        made = await collection_writes.restore_deleted(
            self._knowledge, history, self._audit, change, actor=actor
        )
        if made is None:
            raise KnowledgeVersionNotFound(version)
        return await self._change(history, made)

    async def describe(self, uid: str, description: str, *, actor: str) -> CollectionEntry:
        """Rewrite a collection's description — its README's first paragraph."""
        return await collection_writes.describe_collection(
            self._knowledge, self._audit, uid, description, actor=actor
        )

    # --- the feed -----------------------------------------------------------

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


__all__ = ["KnowledgeHistoryService"]
