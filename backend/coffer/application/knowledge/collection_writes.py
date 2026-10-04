"""Two of a person's writes to knowledge that go beyond one document: a
collection's description, and putting back what a delete removed.

**Describe.** A collection has no title: its heading is its folder name and
what it is about is its README's first paragraph (spec knowledge "Read a
collection's description from its README"). Editing it rewrites that paragraph
in place, as one commit naming the user, audited as an edit of the collection —
and the guide skill is re-rendered, because the description is what an agent
recognises the collection by.

**Restore a delete.** Deleting a document or a whole collection keeps it in the
history (spec knowledge "Restore a deleted collection or document from Recent
changes"). Restoring names the delete's change and puts back every file it
removed, exactly as it was just before, as one new commit naming the user: a
document into its collection; a collection as a new ``resources`` row under its
old name with its documents, README and waiting items. Refused rather than
overwritten when the document, or a collection of that name, exists again.
"""

from __future__ import annotations

import asyncio
import shutil

from coffer.application.audit_service import AuditService
from coffer.application.knowledge.recording import recording
from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.audit import AuditEventType
from coffer.domain.knowledge.entry import CollectionEntry
from coffer.domain.knowledge.errors import (
    CollectionExists,
    KnowledgeNotADelete,
    KnowledgeRestoreConflict,
    KnowledgeVersionNotFound,
)
from coffer.domain.knowledge.history import (
    OP_DELETE,
    OP_REMOVE,
    OP_RESTORE,
    OP_SAVE,
    REMOVED,
    WRITER_USER,
    Change,
)
from coffer.domain.resource import Resource
from coffer.domain.vault.writers import CommitMeta
from coffer.infrastructure.knowledge import catalogue, collection_files, paths
from coffer.infrastructure.knowledge.history import KnowledgeHistory


async def describe_collection(
    knowledge: KnowledgeService, audit: AuditService, uid: str, description: str, *, actor: str
) -> CollectionEntry:
    """Make ``description`` the opening paragraph of the collection's README."""
    row = await knowledge.collection(uid)
    meta = CommitMeta(
        WRITER_USER, OP_SAVE, f"Describe collection {row.name}", actor=actor, collection=row.name
    )
    async with recording(knowledge.history, meta) as tx:
        await asyncio.to_thread(collection_files.write_description, row.name, description)
        tx.touch(f"{row.name}/{paths.README_NAME}")
    await audit.record(
        AuditEventType.KNOWLEDGE_EDITED.value,
        resource=row,
        actor=actor,
        details={"path": f"{row.name}/{paths.README_NAME}", "description": True},
    )
    await knowledge.catalogue_changed()
    listed = {c.uid: c for c in await knowledge.list_collections()}
    return listed.get(row.uid) or CollectionEntry(
        uid=row.uid,
        name=row.name,
        description=catalogue.readme_description(row.name),
        folder_path=str(paths.collection_dir(row.name)),
    )


def _removed(change: Change) -> list[str]:
    return [d.path for d in change.documents if d.status == REMOVED]


async def restore_deleted(
    knowledge: KnowledgeService,
    history: KnowledgeHistory,
    audit: AuditService,
    change: Change,
    *,
    actor: str,
) -> str | None:
    """Put back what the delete ``change`` removed; the new commit's version."""
    operation = change.meta.operation
    if operation not in (OP_DELETE, OP_REMOVE):
        raise KnowledgeNotADelete(change.version)
    removed = _removed(change)
    if not removed:
        raise KnowledgeVersionNotFound(change.version)
    before = f"{change.version}^"
    new_collection = operation == OP_REMOVE
    if new_collection:
        name = change.meta.collection or change.collections[0]
        if name in await knowledge.collection_names() or paths.collection_dir(name).exists():
            raise CollectionExists(name)
        summary = f"Restore collection {name}"
        existing: Resource | None = None
    else:
        name = removed[0].split("/", 1)[0]
        existing = await knowledge.require_collection(removed[0])
        for relpath in removed:
            if paths.resolve(relpath).exists():
                raise KnowledgeRestoreConflict(change.version, relpath)
        summary = f"Restore {removed[0]}"
    meta = CommitMeta(
        WRITER_USER,
        OP_RESTORE,
        summary,
        actor=actor,
        collection=name,
        restored_from=change.version,
    )
    row = existing
    async with recording(history, meta) as tx:
        try:
            if new_collection:
                tx.touch(name)
                await asyncio.to_thread(paths.collection_dir(name).mkdir, parents=True)
            for relpath in removed:
                raw = await asyncio.to_thread(history.show, before, relpath)
                if raw is None:
                    continue
                tx.touch(relpath)
                await asyncio.to_thread(collection_files.restore_file, relpath, raw)
            if new_collection:
                # The row goes last: a collection without files must never be
                # registered, and a failed restore must be retryable.
                row = await knowledge.register_row(name, actor=actor)
        except BaseException:
            if new_collection:
                await asyncio.to_thread(shutil.rmtree, paths.collection_dir(name), True)
            raise
    assert row is not None
    await audit.record(
        AuditEventType.KNOWLEDGE_EDITED.value,
        resource=row,
        actor=actor,
        details={"restored_from": change.version, "paths": removed},
    )
    await knowledge.catalogue_changed()
    return tx.version


__all__ = ["describe_collection", "restore_deleted"]
