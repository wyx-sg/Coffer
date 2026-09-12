"""SQLAlchemy repository for the single backup-remote row (spec vault-export-import).

Kept out of ``repos.py`` for the same reason ``retention_repo.py`` is: that
module is already at its file-size budget, and a table with its own lifecycle
reads better next to the rules that govern it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.sync.backup import BackupRemote, BackupRun, BackupRunStatus
from coffer.infrastructure.persistence.models import SyncRemoteModel

_ROW_ID = 1


class SqlAlchemySyncRemoteRepo:
    """Reads and writes the one ``sync_remotes`` row.

    ``set`` upserts rather than inserts: the schema allows exactly one row, so
    pointing Coffer at a different repository replaces the first remote instead
    of failing on a constraint the user never asked about.

    ``record_run`` is deliberately a no-op when no remote is configured — a run
    result belongs to a remote, and clearing the remote mid-run should discard
    the result rather than resurrect the row it described.
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

    async def record_run(self, run: BackupRun) -> None:
        async with self._sm() as session:
            row = await session.get(SyncRemoteModel, _ROW_ID)
            if row is None:
                return
            row.last_run_at = run.ran_at or datetime.now(tz=UTC)
            row.last_status = str(run.status)
            row.last_error = run.error
            if run.commit is not None:
                # A push-failed run reports no new commit; keeping the previous
                # one tells the user which revision is still waiting to go out.
                row.last_commit = run.commit
            row.updated_at = datetime.now(tz=UTC)
            await session.commit()

    async def last_run(self) -> BackupRun | None:
        async with self._sm() as session:
            stmt = select(SyncRemoteModel).where(SyncRemoteModel.id == _ROW_ID)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None or row.last_status is None:
                return None
            return BackupRun(
                status=BackupRunStatus(row.last_status),
                commit=row.last_commit,
                error=row.last_error,
                # SQLite hands back naive datetimes; everything stored here was
                # written in UTC, so re-stamping the zone is a read-side fix
                # rather than a conversion.
                ran_at=row.last_run_at.replace(tzinfo=UTC) if row.last_run_at else None,
            )
