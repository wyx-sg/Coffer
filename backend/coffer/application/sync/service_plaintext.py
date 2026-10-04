""" "Push anyway" for a round that found a plaintext secret
(spec vault-sync "Refuse to push a plaintext secret").

The detection can be wrong — an example key in a document, a test value —
and only the person can say so. "Push anyway" allows exactly the blobs the
last round found, records who allowed which files in the audit log, and runs
a round. A file changed since is a new blob and is read again.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from coffer.application.sync import round_plaintext_context
from coffer.domain.audit import AuditEventType
from coffer.domain.sync.errors import SyncNoPlaintextFound
from coffer.domain.sync.plaintext import PlaintextContext
from coffer.domain.sync.rounds import RoundRecord, RoundStatus

if TYPE_CHECKING:  # pragma: no cover - typing only
    from coffer.application.audit_service import AuditService
    from coffer.application.sync.round_engine import RoundEngine
    from coffer.application.sync.round_ports import RoundHistoryPort


class PlaintextMixin:
    """Declares what it borrows from ``SyncService``, which assigns each."""

    _engine: RoundEngine
    _history: RoundHistoryPort
    _audit: AuditService

    async def run(self, *, trigger: str = "manual") -> RoundRecord:  # pragma: no cover
        raise NotImplementedError

    async def _last_plaintext(self) -> RoundRecord:
        found = await self._history.recent(1)
        last = found[0] if found else None
        if last is None or last.status is not RoundStatus.PLAINTEXT_FOUND or not last.plaintext:
            raise SyncNoPlaintextFound()
        return last

    async def plaintext_context(self, path: str, line: int) -> PlaintextContext:
        """One place the last round found, in its file with every value masked
        (spec vault-sync "Show a plaintext finding in its file"); nothing is
        stored, logged or audited."""
        last = await self._last_plaintext()
        return await asyncio.to_thread(
            round_plaintext_context.context, self._engine.d, last, path, line
        )

    async def push_anyway(self, *, actor: str) -> RoundRecord:
        """Allow what the last round found, audit it, and run a round."""
        last = await self._last_plaintext()
        state = self._engine.d.state
        await asyncio.to_thread(state.allow_plaintext, [f.blob for f in last.plaintext])
        await self._audit.record(
            AuditEventType.SYNC_PLAINTEXT_PUSHED.value,
            actor=actor,
            details={
                "round": last.id,
                "files": sorted({f"{f.path}:{f.line}" for f in last.plaintext}),
            },
        )
        return await self.run(trigger="manual")


__all__ = ["PlaintextMixin"]
