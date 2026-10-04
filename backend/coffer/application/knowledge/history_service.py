"""Reading a collection's history, restoring a version, undoing a pass, and
the recent-changes feed (spec knowledge "Keep every document's history and
undo a pass as a whole", "Follow knowledge changes across collections").

The history is the vault repository's, under ``knowledge/``
(``infrastructure.knowledge.history``); this service is what the surfaces ask.
Every read first commits what changed outside Coffer as ``disk`` writes, so
what it reports is the tree as it is, not as Coffer last wrote it.

Two writes live here, and both are a person's: **restore** puts one version of
one document back as a new commit, which the sweep carries outward like any
edit; **undo** puts every document one curation pass wrote or retired back
exactly as it was before the pass, as one commit — refused, naming the
document, when a later commit changed any of them. Undo records each restored
document as settled by curation, so the sweep does not read the undo as an
edit and redo the pass. A pass that merged nothing (``no_model``, ``too_large`` or
one that gave up) turned its item into a document as it stood, so undoing it puts
that item back in the inbox: removing the document would otherwise lose the
knowledge. A pass that merged its item leaves the item gone; its text stays in
the history.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
from collections.abc import Callable
from datetime import UTC, datetime

from coffer.application.audit_service import AuditService
from coffer.application.knowledge import collection_writes
from coffer.application.knowledge.recording import recording, settle
from coffer.application.knowledge.service import KnowledgeService
from coffer.application.knowledge.undo_handoff import undo_pass_handoff
from coffer.domain.audit import AuditEventType
from coffer.domain.git_handoff import git_missing_details
from coffer.domain.knowledge.entry import CollectionEntry, KnowledgeFile
from coffer.domain.knowledge.errors import (
    KnowledgeFileNotFound,
    KnowledgeHistoryUnavailable,
    KnowledgeNotAPass,
    KnowledgeUndoConflict,
    KnowledgeVersionNotFound,
)
from coffer.domain.knowledge.history import (
    OP_PASS,
    OP_RESTORE,
    OP_UNDO,
    REMOVED,
    WRITER_USER,
    Change,
    ChangeDetail,
    ChangesPage,
    DocumentDiff,
    DocumentVersion,
    WaitingItem,
)
from coffer.domain.pagination import decode_cursor, encode_cursor
from coffer.domain.resource import Resource
from coffer.domain.vault.writers import CommitMeta
from coffer.infrastructure.knowledge import collection_files, fs, inbox, paths
from coffer.infrastructure.knowledge.frontmatter import split_frontmatter
from coffer.infrastructure.knowledge.history import KnowledgeHistory

#: The cursor tag of the feed (spec resource-framework "Page growing lists by
#: an opaque cursor").
_FEED = "knowledge_changes"
#: How many commits one read of git asks for while filling a page.
_BATCH = 100
_INBOX_SEGMENT = f"/{paths.INBOX_DIR_NAME}/"


#: The pass outcomes that promoted the item as it stood instead of merging it
#: (spec knowledge "Report every pass outcome as a status").
_PROMOTING_STATUSES = frozenset({"no_model", "too_large", "truncated"})


def _instant(stamp: str) -> float:
    """An item's ``created_at`` as a sortable number; unreadable sorts oldest."""
    try:
        parsed = datetime.fromisoformat(stamp)
    except ValueError:
        return 0.0
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).timestamp()


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
        """Recent changes newest first, with the items still waiting."""
        filters = {"collection": collection}
        position = decode_cursor(cursor, list_tag=_FEED, filters=filters)
        names = await self._knowledge.collection_names()
        if collection is not None:
            await self._knowledge.require_collection(collection)
            names = [collection]
        history = await self._settled()
        found = await asyncio.to_thread(
            self._fill, history, collection, str(position[0]) if position else None, limit
        )
        page = found[:limit]
        more = len(found) > limit
        return ChangesPage(
            changes=tuple(page),
            waiting=tuple(await self._waiting(names)),
            next_cursor=encode_cursor(_FEED, filters, [page[-1].version]) if more else None,
        )

    def _fill(
        self, history: KnowledgeHistory, collection: str | None, after: str | None, limit: int
    ) -> list[Change]:
        """Up to ``limit + 1`` visible changes after ``after``, in log order.

        A submission still waiting touches only the inbox, and is a waiting
        item rather than a change, so a commit left with no document is not
        listed; inbox paths are dropped from a pass's documents too.
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

    async def _waiting(self, names: list[str]) -> list[WaitingItem]:
        out: list[WaitingItem] = []
        for name in names:
            items = await asyncio.to_thread(inbox.inbox_items, name)
            if not items:
                continue
            authors = await self._authors(await self._knowledge.require_collection(name))
            for item in items:
                with contextlib.suppress(KnowledgeFileNotFound):
                    found = await asyncio.to_thread(inbox.read_material, name, item)
                    out.append(
                        WaitingItem(
                            collection=name,
                            path=found.path,
                            title=found.title,
                            submitted_by=authors.get(item, found.actor),
                            submitted_at=found.created_at,
                        )
                    )
        # Newest submitted first across every collection, like the timeline beside
        # it; the inbox's own oldest-first order is curation's, not the reader's.
        out.sort(key=lambda w: _instant(w.submitted_at), reverse=True)
        return out

    async def _authors(self, row: Resource) -> dict[str, str]:
        """Inbox item name -> who submitted it, from the audit log."""
        try:
            entries = await self._audit.query(
                resource=row,
                event_type=AuditEventType.KNOWLEDGE_WRITTEN.value,
                limit=500,
            )
        except Exception:
            return {}
        out: dict[str, str] = {}
        for entry in reversed(entries):
            item = (entry.details or {}).get("item")
            if item:
                out[str(item)] = entry.actor
        return out

    async def change(self, version: str) -> ChangeDetail:
        """One change in full: every document it touched, with its diff."""
        history = await self._settled()
        change = await self._change(history, version)
        documents = tuple(d for d in change.documents if _is_document(d.path))
        diffs = []
        for doc in documents:
            text = await asyncio.to_thread(history.diff, change.version, doc.path)
            diffs.append(
                DocumentDiff(
                    path=doc.path,
                    status=doc.status,
                    diff=text,
                    added=doc.added,
                    removed=doc.removed,
                )
            )
        return ChangeDetail(
            change=dataclasses.replace(change, documents=documents), diffs=tuple(diffs)
        )

    # --- undo ---------------------------------------------------------------

    async def undo(self, version: str, *, actor: str) -> Change:
        """Put back every document the pass ``version`` wrote or retired."""
        history = await self._settled()
        change = await self._change(history, version)
        if change.meta.operation != OP_PASS:
            raise KnowledgeNotAPass(version)
        documents = [d.path for d in change.documents if _is_document(d.path)]
        # What a promoting pass took out of the inbox goes back, so undoing it
        # loses nothing.
        items = (
            [d.path for d in change.documents if not _is_document(d.path) and d.status == REMOVED]
            if change.meta.status in _PROMOTING_STATUSES
            else []
        )
        changed_since: dict[str, str] = {}
        for relpath in documents:
            later = await asyncio.to_thread(history.later, change.version, relpath)
            if later is not None:
                changed_since[relpath] = later
        if changed_since:
            document, later = next(iter(changed_since.items()))
            raise KnowledgeUndoConflict(
                change.version,
                document,
                later,
                handoff=undo_pass_handoff(
                    root=paths.knowledge_root(),
                    repo=history.writer().repo.root,
                    prefix=paths.VAULT_PREFIX,
                    change=change,
                    documents=documents,
                    changed_since=changed_since,
                ),
            )
        meta = CommitMeta(
            WRITER_USER,
            OP_UNDO,
            f"Undo curation: {change.meta.summary}",
            actor=actor,
            collection=change.meta.collection,
            item=change.meta.item,
            undoes=change.version,
        )
        async with recording(history, meta) as tx:
            for relpath in documents:
                tx.touch(relpath)
                before = await asyncio.to_thread(history.show, f"{change.version}^", relpath)
                if before is None:
                    with contextlib.suppress(KnowledgeFileNotFound):
                        await asyncio.to_thread(fs.delete_file, relpath)
                else:
                    await asyncio.to_thread(fs.write_bytes, relpath, before, settled=True)
            for relpath in items:
                raw = await asyncio.to_thread(history.show, f"{change.version}^", relpath)
                if raw is not None:
                    tx.touch(relpath)
                    await asyncio.to_thread(collection_files.restore_file, relpath, raw)
        if change.meta.collection:
            with contextlib.suppress(Exception):
                row = await self._knowledge.require_collection(change.meta.collection)
                await self._audit.record(
                    AuditEventType.KNOWLEDGE_EDITED.value,
                    resource=row,
                    actor=actor,
                    details={"undo": change.version, "documents": documents, "items": items},
                )
        await self._knowledge.catalogue_changed()
        if tx.version is None:
            raise KnowledgeVersionNotFound(version)
        return await self._change(history, tx.version)


__all__ = ["KnowledgeHistoryService"]
