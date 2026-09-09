"""Delete-path orchestration for the three non-knowledge lanes (handoff /
rules / consolidation-log).

Extracted from ``service.py`` to keep that file under the project's 400-LOC
ceiling, mirroring ``writes.py`` for the knowledge lane. One ``delete_lane``
dispatcher removes the lane file(s) from disk (none of these lanes is indexed
for recall), appends one human-readable line to the store-root
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
from coffer.infrastructure.knowledge.paths import handoff_path, rules_dir
from coffer.infrastructure.knowledge_scope.handoff_files import branch_slug, delete_handoff
from coffer.infrastructure.knowledge_scope.rules_files import delete_rules_lane
from coffer.infrastructure.knowledge_scope.topic_files import (
    append_changelog,
    delete_consolidation_log,
)

if TYPE_CHECKING:
    from coffer.application.knowledge.writes import WriteDeps
    from coffer.domain.knowledge.scope import ResolvedScope

#: The three deletable non-knowledge lanes.
Lane = Literal["handoff", "rules", "consolidation-log"]
#: The lanes carrying a per-file identifier (branch); rules and the
#: consolidation-log are whole-lane / single-file with no identifier.
_KEYED = ("handoff",)


async def delete_lane(
    lane: Lane,
    *,
    deps: WriteDeps,
    resolved: ResolvedScope,
    scope_name: str,
    identifier: str,
    actor: str,
) -> None:
    """Delete one lane file (or the whole rules lane) → changelog append → audit
    + notify. ``identifier`` is the branch (handoff); unused for
    ``rules``/``consolidation-log``."""
    store_dir = resolved.store_dir
    existed = await asyncio.to_thread(_remove_files, lane, store_dir, identifier)
    if not existed:
        raise MemoryNotFound(scope_name, f"{lane}/{identifier}" if lane in _KEYED else lane)
    ident = identifier if lane in _KEYED else None
    # The changelog records every lane delete EXCEPT its own (that's the file
    # being removed — a self-append would resurrect it).
    if lane != "consolidation-log":
        what = f"{lane}/{identifier}" if lane in _KEYED else lane
        line = f"- {datetime.now(tz=UTC).isoformat()} {actor} deleted {what}"
        await asyncio.to_thread(append_changelog, store_dir, line)
    await deps.audit_and_notify(
        AuditEventType.MEMORY_DELETED,
        scope_name=scope_name,
        actor=actor,
        details={"lane": lane, "identifier": ident},
    )


def _remove_files(lane: Lane, store_dir: Path, identifier: str) -> bool:
    """Remove the lane's on-disk file(s); return whether anything existed."""
    if lane == "handoff":
        return delete_handoff(handoff_path(store_dir, branch_slug(identifier)))
    if lane == "rules":
        return delete_rules_lane(rules_dir(store_dir))
    return delete_consolidation_log(store_dir)
