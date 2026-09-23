"""This machine's convergence state, in the one place that never travels.

Implements ``application.sync.ports.ConvergenceStatePort`` over SQLite. The
storage choice is the design: ``coffer.db`` is already excluded from the bundle
(spec vault-sync "Keep reach machine-local"), so state kept here cannot
accidentally be published the way a file beside the working tree could be. A
pointer that travelled would be some other machine's claim about what this
vault has absorbed, and every diff the round takes rests on it being this
machine's own.

Three facts live here, and none of them are derivable from the repository:

* the **pointer** — the commit this vault has provably absorbed,
* the **held paths** — the retry and not-applicable sets the exporter must
  leave in the working tree,
* the **pending confirmation** — a round the deletion guard stopped, stored
  whole rather than recomputed, so the user's "yes" means what they were shown.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.sync.convergence import GuardDirection, PendingConfirmation
from coffer.infrastructure.persistence.models import ConvergenceStateModel, SyncHeldPathModel

_ROW_ID = 1


def _pending_to_json(pending: PendingConfirmation) -> str:
    return json.dumps(
        {
            "direction": pending.direction.value,
            "commit": pending.commit,
            "remote_tip": pending.remote_tip,
            "breaches": [list(b) for b in pending.breaches],
            "paths": list(pending.paths),
            "raised_at": pending.raised_at.isoformat(),
        },
        sort_keys=True,
    )


def _pending_from_json(raw: str) -> PendingConfirmation | None:
    """Parse a held round back, or None when the row cannot be read.

    None rather than an exception: a confirmation this build cannot parse would
    otherwise wedge every future round behind a held state nobody can clear,
    and "nothing is held" is the state a round can actually proceed from.
    """
    try:
        data = json.loads(raw)
        return PendingConfirmation(
            direction=GuardDirection(data["direction"]),
            commit=str(data["commit"]),
            remote_tip=_opt(data.get("remote_tip")),
            breaches=tuple((str(a), int(d), int(t)) for a, d, t in data.get("breaches", [])),
            paths=tuple(str(p) for p in data.get("paths", [])),
            raised_at=datetime.fromisoformat(data["raised_at"]),
        )
    except (ValueError, TypeError, KeyError):
        return None


class SqlAlchemyConvergenceStateRepo:
    """Implements ``application.sync.ports.ConvergenceStatePort`` structurally."""

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    # --- pointer ------------------------------------------------------------

    async def pointer(self) -> str | None:
        async with self._sm() as session:
            row = await session.get(ConvergenceStateModel, _ROW_ID)
            return row.pointer if row is not None else None

    async def set_pointer(self, commit: str) -> None:
        await self._update(pointer=commit)

    # --- held paths ---------------------------------------------------------

    async def clear_pointer(self) -> None:
        async with self._sm() as session, session.begin():
            row = await session.get(ConvergenceStateModel, _ROW_ID)
            if row is not None:
                row.pointer = None

    async def clear_holds(self) -> None:
        async with self._sm() as session, session.begin():
            await session.execute(delete(SyncHeldPathModel))

    async def held_paths(self) -> tuple[set[str], set[str]]:
        async with self._sm() as session:
            rows = (await session.execute(select(SyncHeldPathModel))).scalars().all()
        retry = {r.path for r in rows if r.applicable}
        not_applicable = {r.path for r in rows if not r.applicable}
        return retry, not_applicable

    async def hold(self, path: str, *, applicable: bool) -> None:
        """Record a path the export must preserve.

        An existing hold is re-stamped rather than left alone, and its
        applicability is overwritten: a path that failed for a machine-local
        reason last round and a transient one this round is now pending, and
        vice versa. The most recent attempt is the one that knows.
        """
        async with self._sm() as session:
            row = await session.get(SyncHeldPathModel, path)
            if row is None:
                row = SyncHeldPathModel(path=path)
                session.add(row)
            row.applicable = applicable
            row.held_at = datetime.now(tz=UTC)
            await session.commit()

    async def release(self, path: str) -> None:
        async with self._sm() as session:
            await session.execute(delete(SyncHeldPathModel).where(SyncHeldPathModel.path == path))
            await session.commit()

    # --- pending confirmation ----------------------------------------------

    async def pending(self) -> PendingConfirmation | None:
        async with self._sm() as session:
            row = await session.get(ConvergenceStateModel, _ROW_ID)
        if row is None or row.pending_json is None:
            return None
        return _pending_from_json(row.pending_json)

    async def set_pending(self, pending: PendingConfirmation | None) -> None:
        await self._update(pending_json=_pending_to_json(pending) if pending else None)

    # --- internals ----------------------------------------------------------

    async def _update(self, **fields: Any) -> None:
        """Upsert the singleton row. It is created on first write rather than
        by the migration, so a vault that has never converged carries no row
        and ``pointer()`` answers None without one."""
        async with self._sm() as session:
            row = await session.get(ConvergenceStateModel, _ROW_ID)
            if row is None:
                row = ConvergenceStateModel(id=_ROW_ID)
                session.add(row)
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = datetime.now(tz=UTC)
            await session.commit()


def _opt(value: object) -> str | None:
    """A stored tip that is missing or blank reads as "unknown", which makes a
    confirmation re-check the guard rather than waive it — the safe direction."""
    return str(value) if isinstance(value, str) and value else None
