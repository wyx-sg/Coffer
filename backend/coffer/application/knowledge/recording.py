"""Record a knowledge write as one commit naming its writer (spec knowledge
"Keep every document's history and undo a pass as a whole").

The service's writes and the curation pass both go through here, so the rule
is stated once: open the operation's commit (which first commits whatever
changed outside Coffer, as an edit on disk), do the write, touch what it wrote,
commit exactly that. The git calls run off the event loop. With no history
wired — a unit test, a machine with no git — the operation runs unrecorded and
nothing else changes.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.domain.knowledge.entry import ACTOR_AGENT
from coffer.domain.knowledge.history import WRITER_AGENT, WRITER_USER, ChangeMeta
from coffer.domain.resource import Resource
from coffer.infrastructure.knowledge.history import KnowledgeHistory, Transaction


@contextlib.asynccontextmanager
async def recording(
    history: KnowledgeHistory | None, meta: ChangeMeta
) -> AsyncIterator[Transaction]:
    """One operation's commit around the block. The commit is made even when
    the block raises, so a write that half-landed is never left unrecorded."""
    tx = await asyncio.to_thread(history.begin, meta) if history else Transaction(None, meta)
    try:
        yield tx
    finally:
        await asyncio.to_thread(tx.commit)


def writer_of(actor_kind: str) -> str:
    """The history writer for a surface's actor kind (``agent`` or ``user``)."""
    return WRITER_AGENT if actor_kind == ACTOR_AGENT else WRITER_USER


async def settle(history: KnowledgeHistory | None) -> None:
    """Commit what changed outside Coffer — sync's paths, then edits on disk."""
    if history is not None:
        await asyncio.to_thread(history.settle)


#: How far back a pass looks for the submission of the item it curates. An item
#: waits at most a sweep or two, so its event is among the collection's latest.
_SUBMISSIONS_SCANNED = 500


async def submitted_by(audit: AuditService | None, row: Resource, name: str) -> str | None:
    """Who submitted the inbox item ``name``, from its ``knowledge_written``
    audit event — the agent's name, or ``user``. ``None`` when no event names
    it (material older than the event's ``item`` field, or migrated)."""
    if audit is None:
        return None
    try:
        entries = await audit.query(
            resource=row,
            event_type=AuditEventType.KNOWLEDGE_WRITTEN.value,
            limit=_SUBMISSIONS_SCANNED,
        )
    except Exception:
        return None
    for entry in entries:
        if (entry.details or {}).get("item") == name:
            return entry.actor
    return None


async def item_author(service: object, row: Resource, name: str, fallback: str) -> str:
    """The author a pass names for its item: the audit event's actor, else the
    item's own frontmatter ``actor`` (``user`` or ``agent``)."""
    found = await submitted_by(getattr(service, "_audit", None), row, name)
    return found or fallback


__all__ = ["item_author", "recording", "settle", "submitted_by", "writer_of"]
