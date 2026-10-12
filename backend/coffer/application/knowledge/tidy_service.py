"""A tidy as one change (spec knowledge "Record a tidy as one change").

The agent the Tidy prompt starts runs ``coffer knowledge tidy-start <collection>``
before it edits anything and ``coffer knowledge tidy-finish <collection>`` with
its report when it is done. In between, the collection is paused in the vault
writer: the agent's edits stay in the working tree, so the vault scanner, the
knowledge sweep and a sync round leave them alone. Finishing commits them all
as one ``tidy`` change whose summary is the report, so the collection's change
log shows the tidy as one entry the person can read and undo.

An agent that never finishes must not pause a collection for ever: the sweep
closes a tidy whose collection has not changed for ``IDLE_S``, committing what
it did with no report. A tidy that changed nothing commits nothing.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from coffer.application.knowledge.recording import settle
from coffer.application.knowledge.service import KnowledgeService
from coffer.domain.audit import AuditEventType
from coffer.domain.knowledge.history import OP_TIDY, WRITER_AGENT, Change
from coffer.domain.vault.writers import CommitMeta
from coffer.infrastructure.knowledge.history import KnowledgeHistory
from coffer.infrastructure.knowledge.tidy_runs import TIDY_RUNS, TidyRuns

logger = logging.getLogger(__name__)

#: How long a tidy's collection may sit unchanged before the sweep closes it.
IDLE_S = 30 * 60
#: A tidy's ``Coffer-Status``: its agent finished it with a report, or the
#: sweep closed it after its collection sat unchanged.
TIDY_REPORTED = "reported"
TIDY_EXPIRED = "expired"
#: The longest report kept; a commit summary is one line.
MAX_REPORT = 4000


@dataclass(frozen=True)
class TidyStatus:
    """Where a collection's tidy stands."""

    collection: str
    running: bool
    #: When the open tidy started (seconds since the epoch); ``None`` when none is open.
    started_at: float | None = None


def _summary(collection: str, report: str) -> str:
    text = " ".join(report.split())
    if not text:
        return f"Tidied {collection}"
    return text if len(text) <= MAX_REPORT else text[: MAX_REPORT - 1] + "…"


class TidyService:
    def __init__(
        self,
        *,
        knowledge: KnowledgeService,
        history: KnowledgeHistory | None,
        runs: TidyRuns = TIDY_RUNS,
        clock: Callable[[], float] = time.monotonic,
        wall: Callable[[], float] = time.time,
    ) -> None:
        self._knowledge = knowledge
        self._history = history
        self._runs = runs
        self._clock = clock
        self._wall = wall

    def status(self, collection: str) -> TidyStatus:
        run = self._runs.get(collection)
        return TidyStatus(
            collection=collection,
            running=run is not None,
            started_at=run.started_at if run else None,
        )

    async def start(self, uid: str, *, actor: str) -> TidyStatus:
        """Open a tidy of the collection. What changed in it before is committed
        first, as the ``disk`` edit it is, so the tidy's change holds only the
        agent's work. Starting an open tidy again keeps it."""
        row = await self._knowledge.collection(uid)
        if self._runs.get(row.name) is None:
            await settle(self._history)
            history = self._history
            if history is not None:
                await asyncio.to_thread(history.pause_tidies)
                fingerprint = await asyncio.to_thread(history.pending_in, row.name)
            else:
                fingerprint = ()
            run = self._runs.open(row.name, started_at=self._wall(), now=self._clock())
            run.fingerprint = fingerprint
            await self._knowledge.audit.record(
                AuditEventType.KNOWLEDGE_EDITED.value,
                resource=row,
                actor=actor,
                details={"tidy": "started"},
            )
            self._knowledge.announce(row.uid)
        return self.status(row.name)

    async def finish(self, uid: str, report: str, *, actor: str) -> Change | None:
        """Close the collection's tidy and commit what it changed as one
        ``tidy`` change carrying ``report``; ``None`` when it changed nothing.
        Finishing with no tidy open still commits the collection's pending
        edits as a tidy, so an agent that forgot to start loses no grouping of
        what it has not yet had committed."""
        row = await self._knowledge.collection(uid)
        change = await self._close(row.name, report, actor=actor, status=TIDY_REPORTED)
        await self._knowledge.audit.record(
            AuditEventType.KNOWLEDGE_EDITED.value,
            resource=row,
            actor=actor,
            details={
                "tidy": "finished",
                "version": change.version if change else None,
                "count": len(change.documents) if change else 0,
            },
        )
        self._knowledge.announce(row.uid)
        if change is not None:
            await self._knowledge.catalogue_changed()
        return change

    async def _close(
        self, collection: str, report: str, *, actor: str, status: str
    ) -> Change | None:
        self._runs.close(collection)
        history = self._history
        if history is None:
            return None
        meta = CommitMeta(
            WRITER_AGENT,
            OP_TIDY,
            _summary(collection, report),
            actor=actor,
            collection=collection,
            status=status,
        )
        version = await asyncio.to_thread(history.settle_as, collection, meta)
        if version is None:
            return None
        return await asyncio.to_thread(history.change, version)

    async def expire(self) -> list[str]:
        """Close every tidy whose collection has sat unchanged for ``IDLE_S``;
        the collections closed. Run by the knowledge sweep."""
        history = self._history
        closed: list[str] = []
        now = self._clock()
        for run in self._runs.runs():
            fingerprint = (
                await asyncio.to_thread(history.pending_in, run.collection) if history else ()
            )
            if fingerprint != run.fingerprint:
                run.fingerprint = fingerprint
                run.last_activity = now
                continue
            if now - run.last_activity < IDLE_S:
                continue
            try:
                await self._close(run.collection, "", actor="daemon", status=TIDY_EXPIRED)
                closed.append(run.collection)
            except Exception:
                logger.warning("knowledge.tidy.expire_failed", exc_info=True)
        if closed:
            await self._knowledge.catalogue_changed()
        return closed


__all__ = ["IDLE_S", "MAX_REPORT", "TIDY_EXPIRED", "TIDY_REPORTED", "TidyService", "TidyStatus"]
