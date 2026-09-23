"""SQLAlchemy repository for the sync remote and the rounds run against it.

Spec vault-sync. Kept out of ``repos.py`` for the same reason
``retention_repo.py`` is: that module is already at its file-size budget, and a
table with its own lifecycle reads better next to the rules that govern it.

Two tables, one repository, because one round writes both: the remote's
``last_*`` columns are the current state a status surface reads, and
``sync_runs`` is the history a user scrolls. Recording a round writes them in a
single transaction, so the newest history row and the remote's columns can
never describe different rounds.

The remote row carries two different things. The remote's **configuration** — URL,
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
    RunRecord,
)
from coffer.domain.sync.diff import ChangeStatus, DiffSummary, DocChange
from coffer.infrastructure.persistence.models import SyncRemoteModel, SyncRunModel
from coffer.infrastructure.persistence.sync_join_report_json import report_from_json, report_to_json

_ROW_ID = 1

#: How many rounds a history read returns when the caller names no limit. The
#: surface filters and pages in the browser over what it is handed, so this is
#: the window a user can search — generous, and still one small query. The
#: application layer passes its own limit (``service_history.DEFAULT_RUN_LIMIT``)
#: on every call; this is the floor for anything that does not.
_RUNS_LIMIT = 500


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
            "not_applicable": list(run.not_applicable),
            "locked_refs": list(run.locked_refs),
            "pending": _pending_to_json(run.pending) if run.pending else None,
            "join_report": report_to_json(run.join_report) if run.join_report else None,
        },
        sort_keys=True,
    )


def _payload_of(raw: str | None) -> dict[str, Any]:
    """The stored overflow document, or an empty one.

    Unreadable JSON degrades to "the round reported nothing further" rather
    than raising: the status and the commit are in columns, and those are what
    the user acts on.
    """
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _run_of(
    payload: dict[str, Any],
    *,
    status: str,
    started_at: datetime | None,
    finished_at: datetime | None,
    join: str | None,
    commit: str | None,
    error: str | None,
) -> ConvergeRun:
    """Rebuild a round from its columns and its payload.

    Shared by the remote's ``last_*`` columns and the history's rows, which
    store the same round the same way — so a round read out of either place
    reports identically.
    """
    # SQLite hands back naive datetimes; everything stored here was written in
    # UTC, so re-stamping the zone is a read-side fix, not a conversion.
    finished = _utc(finished_at) or datetime.now(tz=UTC)
    return ConvergeRun(
        status=ConvergeStatus(status),
        started_at=_utc(started_at) or finished,
        finished_at=finished,
        join=JoinKind(join) if join else None,
        applied=_summary_from_json(payload.get("applied")),
        published=_summary_from_json(payload.get("published")),
        commit=commit,
        conflicts=tuple(str(p) for p in payload.get("conflicts", [])),
        agent_resolved=tuple(str(p) for p in payload.get("agent_resolved", [])),
        failures=tuple((str(p), str(r)) for p, r in payload.get("failures", [])),
        not_applicable=tuple(str(p) for p in payload.get("not_applicable", [])),
        locked_refs=tuple(str(r) for r in payload.get("locked_refs", [])),
        pending=_pending_from_json(payload.get("pending")),
        join_report=report_from_json(payload.get("join_report")),
        error=error,
    )


class SqlAlchemySyncRemoteRepo:
    """Reads and writes the one ``sync_remotes`` row, and the ``sync_runs`` history.

    ``set`` upserts rather than inserts: the schema allows exactly one row, so
    pointing Coffer at a different repository replaces the first remote instead
    of failing on a constraint the user never asked about.

    ``record_run`` is deliberately a no-op when no remote is configured — a run
    result belongs to a remote, and clearing the remote mid-round should
    discard the result rather than resurrect the row it described. That applies
    to both of its writes: a round discarded from the remote row must not
    survive in the history either.
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
        """Store the round twice, in one transaction.

        Onto the remote row as ``last_*`` — what a status surface reads without
        touching the history — and appended to ``sync_runs``. One commit, so
        the newest history row and those columns can never describe different
        rounds; and both skipped together when there is no remote, so a
        cleared remote discards the round rather than resurrecting a row for it.
        """
        async with self._sm() as session:
            row = await session.get(SyncRemoteModel, _ROW_ID)
            if row is None:
                return
            payload = _run_payload(run)
            row.last_started_at = run.started_at
            row.last_run_at = run.finished_at
            row.last_status = run.status.value
            row.last_join = run.join.value if run.join else None
            row.last_error = run.error
            if run.commit is not None:
                # A push-failed round reports no new commit; keeping the
                # previous one tells the user which revision is still waiting.
                row.last_commit = run.commit
            row.last_run_json = payload
            row.updated_at = datetime.now(tz=UTC)
            session.add(
                SyncRunModel(
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    status=run.status.value,
                    join_kind=run.join.value if run.join else None,
                    # The history records the round as it happened: a
                    # push-failed round landed no commit, and carrying the
                    # previous one forward here — as the remote row must, to
                    # name the revision still waiting — would put a commit on
                    # a row that did not produce it.
                    commit_sha=run.commit,
                    error=run.error,
                    payload_json=payload,
                )
            )
            await session.commit()

    async def refresh_run(self, run: ConvergeRun) -> bool:
        """Re-stamp the newest recorded round instead of appending a new one.

        One outstanding confirmation is one situation, and the timer
        re-deriving it every interval is not news (spec vault-sync "Record one
        outstanding confirmation once"). The round is written over the row that
        first reported it — same ``started_at``, so the moment the vault
        stopped is still readable, with ``finished_at`` and the payload
        refreshed so the row also shows the vault is still ticking — and the
        history grows no second row for it.

        False when there is nothing to refresh, or when the newest row is not
        the same outcome: the caller then records the round normally. The
        status check is the invariant that keeps this from ever writing a held
        round over an unrelated one — something else may have recorded a round
        between two ticks.
        """
        async with self._sm() as session:
            remote = await session.get(SyncRemoteModel, _ROW_ID)
            if remote is None:
                return False
            stmt = (
                select(SyncRunModel)
                .order_by(SyncRunModel.finished_at.desc(), SyncRunModel.id.desc())
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None or row.status != run.status.value:
                return False
            payload = _run_payload(run)
            row.finished_at = run.finished_at
            row.commit_sha = run.commit
            row.error = run.error
            row.payload_json = payload
            remote.last_run_at = run.finished_at
            remote.last_status = run.status.value
            remote.last_error = run.error
            if run.commit is not None:
                remote.last_commit = run.commit
            remote.last_run_json = payload
            remote.updated_at = datetime.now(tz=UTC)
            await session.commit()
            return True

    async def last_run(self) -> ConvergeRun | None:
        async with self._sm() as session:
            stmt = select(SyncRemoteModel).where(SyncRemoteModel.id == _ROW_ID)
            row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None or row.last_status is None:
            return None
        return _run_of(
            _payload_of(row.last_run_json),
            status=row.last_status,
            started_at=row.last_started_at,
            finished_at=row.last_run_at,
            join=row.last_join,
            commit=row.last_commit,
            error=row.last_error,
        )

    async def list_runs(self, limit: int = _RUNS_LIMIT) -> list[RunRecord]:
        """Every round this vault has run, newest first.

        Ordered by ``finished_at`` and then by ``id``, because a fast round can
        finish in the same millisecond it started and SQLite stores that
        timestamp to no finer resolution — without the id the two would come
        back in whatever order the index happened to hold them.
        """
        async with self._sm() as session:
            stmt = (
                select(SyncRunModel)
                .order_by(SyncRunModel.finished_at.desc(), SyncRunModel.id.desc())
                .limit(max(1, limit))
            )
            rows = list((await session.execute(stmt)).scalars())
        return [
            RunRecord(
                id=row.id,
                run=_run_of(
                    _payload_of(row.payload_json),
                    status=row.status,
                    started_at=row.started_at,
                    finished_at=row.finished_at,
                    join=row.join_kind,
                    commit=row.commit_sha,
                    error=row.error,
                ),
            )
            for row in rows
        ]


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _opt(value: object) -> str | None:
    """A stored tip that is missing or blank reads as "unknown", which makes a
    confirmation re-check the guard rather than waive it — the safe direction."""
    return str(value) if isinstance(value, str) and value else None
