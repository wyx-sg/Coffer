"""SQLAlchemy repository for the single sync-remote row (spec vault-sync).

Kept out of ``repos.py`` for the same reason ``retention_repo.py`` is: that
module is already at its file-size budget, and a table with its own lifecycle
reads better next to the rules that govern it.

The row carries two different things. The remote's **configuration** — URL,
branch, credential reference, interval, working tree — is what the user typed,
and it means the same under bidirectional convergence as it did under one-way
backup. The **last round** is what Coffer did with it, and that changed shape
entirely: a run is now a ``ConvergeRun`` with a status, a join kind, a diff in
each direction, conflicts, agent resolutions, per-path failures and possibly a
held confirmation.

Only the fields a status surface reads at a glance are columns. Everything else
is one JSON document, written exactly once, so no column can ever disagree with
the payload beside it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.sync.backup import BackupRemote
from coffer.domain.sync.convergence import (
    ConvergeRun,
    ConvergeStatus,
    GuardDirection,
    JoinKind,
    PendingConfirmation,
)
from coffer.domain.sync.diff import ChangeStatus, DiffSummary, DocChange
from coffer.infrastructure.persistence.models import SyncRemoteModel

_ROW_ID = 1


def _summary_to_json(summary: DiffSummary) -> list[list[str]]:
    return [[c.path, c.status.value] for c in summary.changes]


def _summary_from_json(raw: Any) -> DiffSummary:
    if not isinstance(raw, list):
        return DiffSummary()
    changes = []
    for entry in raw:
        try:
            path, status = entry
            changes.append(DocChange(str(path), ChangeStatus(status)))
        except (TypeError, ValueError):
            continue
    return DiffSummary.of(changes)


def _pending_to_json(pending: PendingConfirmation) -> dict[str, Any]:
    return {
        "direction": pending.direction.value,
        "commit": pending.commit,
        "remote_tip": pending.remote_tip,
        "breaches": [list(b) for b in pending.breaches],
        "paths": list(pending.paths),
        "raised_at": pending.raised_at.isoformat(),
    }


def _pending_from_json(raw: Any) -> PendingConfirmation | None:
    if not isinstance(raw, dict):
        return None
    try:
        return PendingConfirmation(
            direction=GuardDirection(raw["direction"]),
            commit=str(raw["commit"]),
            remote_tip=_opt(raw.get("remote_tip")),
            breaches=tuple((str(a), int(d), int(t)) for a, d, t in raw.get("breaches", [])),
            paths=tuple(str(p) for p in raw.get("paths", [])),
            raised_at=datetime.fromisoformat(raw["raised_at"]),
        )
    except (ValueError, TypeError, KeyError):
        return None


def _run_payload(run: ConvergeRun) -> str:
    """Everything about a round that is not already a column."""
    return json.dumps(
        {
            "applied": _summary_to_json(run.applied),
            "published": _summary_to_json(run.published),
            "conflicts": list(run.conflicts),
            "agent_resolved": list(run.agent_resolved),
            "failures": [list(f) for f in run.failures],
            "locked_refs": list(run.locked_refs),
            "pending": _pending_to_json(run.pending) if run.pending else None,
        },
        sort_keys=True,
    )


def _payload_of(row: SyncRemoteModel) -> dict[str, Any]:
    """The stored overflow document, or an empty one.

    Unreadable JSON degrades to "the round reported nothing further" rather
    than raising: the status and the commit are in columns, and those are what
    the user acts on.
    """
    if not row.last_run_json:
        return {}
    try:
        data = json.loads(row.last_run_json)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


class SqlAlchemySyncRemoteRepo:
    """Reads and writes the one ``sync_remotes`` row.

    ``set`` upserts rather than inserts: the schema allows exactly one row, so
    pointing Coffer at a different repository replaces the first remote instead
    of failing on a constraint the user never asked about.

    ``record_run`` is deliberately a no-op when no remote is configured — a run
    result belongs to a remote, and clearing the remote mid-round should
    discard the result rather than resurrect the row it described.
    """

    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def get(self) -> BackupRemote | None:
        async with self._sm() as session:
            row = await session.get(SyncRemoteModel, _ROW_ID)
            if row is None:
                return None
            return BackupRemote(
                url=row.url,
                branch=row.branch,
                credential_ref=row.credential_ref,
                include_credentials=row.include_credentials,
                interval_seconds=row.interval_seconds,
                enabled=row.enabled,
                worktree_path=row.worktree_path,
            )

    async def set(self, remote: BackupRemote) -> None:
        async with self._sm() as session:
            row = await session.get(SyncRemoteModel, _ROW_ID)
            if row is None:
                row = SyncRemoteModel(id=_ROW_ID)
                session.add(row)
            row.url = remote.url
            row.branch = remote.branch
            row.credential_ref = remote.credential_ref
            row.include_credentials = remote.include_credentials
            row.interval_seconds = remote.interval_seconds
            row.enabled = remote.enabled
            row.worktree_path = remote.worktree_path
            row.updated_at = datetime.now(tz=UTC)
            await session.commit()

    async def clear(self) -> None:
        async with self._sm() as session:
            await session.execute(delete(SyncRemoteModel).where(SyncRemoteModel.id == _ROW_ID))
            await session.commit()

    async def record_run(self, run: ConvergeRun) -> None:
        async with self._sm() as session:
            row = await session.get(SyncRemoteModel, _ROW_ID)
            if row is None:
                return
            row.last_started_at = run.started_at
            row.last_run_at = run.finished_at
            row.last_status = run.status.value
            row.last_join = run.join.value if run.join else None
            row.last_error = run.error
            if run.commit is not None:
                # A push-failed round reports no new commit; keeping the
                # previous one tells the user which revision is still waiting.
                row.last_commit = run.commit
            row.last_run_json = _run_payload(run)
            row.updated_at = datetime.now(tz=UTC)
            await session.commit()

    async def last_run(self) -> ConvergeRun | None:
        async with self._sm() as session:
            stmt = select(SyncRemoteModel).where(SyncRemoteModel.id == _ROW_ID)
            row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None or row.last_status is None:
            return None
        payload = _payload_of(row)
        # SQLite hands back naive datetimes; everything stored here was written
        # in UTC, so re-stamping the zone is a read-side fix, not a conversion.
        finished = _utc(row.last_run_at) or datetime.now(tz=UTC)
        return ConvergeRun(
            status=ConvergeStatus(row.last_status),
            started_at=_utc(row.last_started_at) or finished,
            finished_at=finished,
            join=JoinKind(row.last_join) if row.last_join else None,
            applied=_summary_from_json(payload.get("applied")),
            published=_summary_from_json(payload.get("published")),
            commit=row.last_commit,
            conflicts=tuple(str(p) for p in payload.get("conflicts", [])),
            agent_resolved=tuple(str(p) for p in payload.get("agent_resolved", [])),
            failures=tuple((str(p), str(r)) for p, r in payload.get("failures", [])),
            locked_refs=tuple(str(r) for r in payload.get("locked_refs", [])),
            pending=_pending_from_json(payload.get("pending")),
            error=row.last_error,
        )


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _opt(value: object) -> str | None:
    """A stored tip that is missing or blank reads as "unknown", which makes a
    confirmation re-check the guard rather than waive it — the safe direction."""
    return str(value) if isinstance(value, str) and value else None
