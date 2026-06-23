"""Delete-path orchestration for the four non-knowledge lanes (journal /
handoff / rules / consolidation-log).

Extracted from ``service.py`` to keep that file under the project's 400-LOC
ceiling, mirroring ``writes.py`` for the knowledge lane. One ``delete_lane``
dispatcher removes the lane file(s) from disk, drops recall-index rows for the
single indexed lane (journal — keyed by ``journal-<period>``; handoff/rules are
NOT indexed), appends one human-readable line to the store-root
``consolidation-log.md`` (EXCEPT the changelog's own delete, which must not
self-append), and records a ``MEMORY_DELETED`` audit event.

Deleting a missing lane file raises ``MemoryNotFound`` so the HTTP layer's
domain-error handler maps it to a 404, matching the fact-delete semantics.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from coffer.domain.audit import AuditEventType
from coffer.domain.errors import MemoryNotFound
from coffer.infrastructure.knowledge.paths import handoff_path, journal_path, rules_dir
from coffer.infrastructure.memory.handoff_files import branch_slug, delete_handoff
from coffer.infrastructure.memory.journal_files import delete_journal_file, journal_doc_id
from coffer.infrastructure.memory.rules_files import delete_rules_lane
from coffer.infrastructure.memory.topic_files import append_changelog, delete_consolidation_log

if TYPE_CHECKING:
    from coffer.application.memory.writes import WriteDeps
    from coffer.domain.memory.scope import ResolvedScope

#: The four deletable non-knowledge lanes.
Lane = Literal["journal", "handoff", "rules", "consolidation-log"]
#: The lanes carrying a per-file identifier (period / branch); rules and the
#: consolidation-log are whole-lane / single-file with no identifier.
_KEYED = ("journal", "handoff")


async def delete_lane(
    lane: Lane,
    *,
    deps: WriteDeps,
    resolved: ResolvedScope,
    store_name: str,
    identifier: str,
    actor: str,
) -> None:
    """Delete one lane file (or the whole rules lane) → drop the journal lane's
    index rows → changelog append → audit + notify. ``identifier`` is the period
    (journal) or branch (handoff); unused for ``rules``/``consolidation-log``."""
    store_dir = resolved.store_dir
    existed = await asyncio.to_thread(_remove_files, lane, store_dir, identifier)
    if not existed:
        raise MemoryNotFound(store_name, f"{lane}/{identifier}" if lane in _KEYED else lane)
    # The journal lane participates in recall (FR-043) — drop its index rows like
    # a fact; handoff/rules/consolidation-log are not indexed.
    if lane == "journal":
        store_ref = deps.store_ref(store_name, resolved.project_id)
        await deps.reconciler.remove_one(store=store_ref, fact_id=journal_doc_id(identifier))
    ident = identifier if lane in _KEYED else None
    # The changelog records every lane delete EXCEPT its own (that's the file
    # being removed — a self-append would resurrect it).
    if lane != "consolidation-log":
        what = f"{lane}/{identifier}" if lane in _KEYED else lane
        line = f"- {datetime.now(tz=UTC).isoformat()} {actor} deleted {what}"
        await asyncio.to_thread(append_changelog, store_dir, line)
    await deps.audit_and_notify(
        AuditEventType.MEMORY_DELETED,
        store_name=store_name,
        actor=actor,
        details={"lane": lane, "identifier": ident},
    )


def _remove_files(lane: Lane, store_dir: Path, identifier: str) -> bool:
    """Remove the lane's on-disk file(s); return whether anything existed."""
    if lane == "journal":
        return delete_journal_file(journal_path(store_dir, identifier))
    if lane == "handoff":
        return delete_handoff(handoff_path(store_dir, branch_slug(identifier)))
    if lane == "rules":
        return delete_rules_lane(rules_dir(store_dir))
    return delete_consolidation_log(store_dir)
