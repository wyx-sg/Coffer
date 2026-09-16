"""SQLAlchemy RetentionRepo — retention-policy reads/writes and the prune/archive sweep.

Split out of ``repos.py`` to keep that module within the file-size budget; the
public name ``SqlAlchemyRetentionRepo`` is re-exported from ``repos`` so existing
import sites keep working.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.application.retention_registry import PrunableTable, UnknownPrunableTable
from coffer.domain.retention import RetentionPolicy
from coffer.infrastructure.persistence.models import RetentionPolicyModel


def allowlist_from_registry(tables: Iterable[PrunableTable]) -> dict[str, set[str]]:
    """The ``{sql_table: {columns}}`` allowlist a set of registrations implies.

    A ``delete`` entry permits its timestamp column on its table; an ``archive``
    entry additionally permits the column it stamps. Two entries sharing a table
    (the conversations archive/delete pair) merge into one set. Only ever fed
    from the composition root's registry, so the identifiers that reach the SQL
    below are exactly the ones the code registered.
    """
    allow: dict[str, set[str]] = {}
    for table in tables:
        columns = allow.setdefault(table.sql_table, set())
        columns.add(table.timestamp_column)
        if table.archive_set_column is not None:
            columns.add(table.archive_set_column)
    return allow


def _retention_to_domain(row: RetentionPolicyModel) -> RetentionPolicy:
    return RetentionPolicy(
        table_name=row.table_name,
        retention_days=row.retention_days,
        last_pruned_at=row.last_pruned_at.replace(tzinfo=UTC)
        if row.last_pruned_at is not None
        else None,
        last_pruned_rows=row.last_pruned_rows,
        updated_at=row.updated_at.replace(tzinfo=UTC) if row.updated_at else datetime.now(tz=UTC),
    )


class SqlAlchemyRetentionRepo:
    """Concrete RetentionRepo against the `retention_policies` table.

    `delete_older_than` / `archive_older_than` validate table+column against
    ``allowlist`` before constructing any SQL, and never accept a user-supplied
    table name. The allowlist is required and has no default, so the identifiers
    that can reach the SQL below are always the ones some caller registered:
    derive it from the registry those same registrations built
    (:func:`allowlist_from_registry`) and there is one source of truth for
    what is sweepable.
    """

    def __init__(
        self,
        sm: async_sessionmaker,  # type: ignore[type-arg]
        *,
        allowlist: Mapping[str, set[str]],
    ) -> None:
        self._sm = sm
        self._allowlist: Mapping[str, set[str]] = allowlist

    async def get(self, table_name: str) -> RetentionPolicy:
        async with self._sm() as session:
            stmt = select(RetentionPolicyModel).where(RetentionPolicyModel.table_name == table_name)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise UnknownPrunableTable(f"no retention policy registered for {table_name!r}")
            return _retention_to_domain(row)

    async def list(self) -> list[RetentionPolicy]:
        async with self._sm() as session:
            rows = (await session.execute(select(RetentionPolicyModel))).scalars().all()
            return [_retention_to_domain(r) for r in rows]

    async def upsert(self, table_name: str, retention_days: int | None) -> None:
        async with self._sm() as session:
            stmt = select(RetentionPolicyModel).where(RetentionPolicyModel.table_name == table_name)
            row = (await session.execute(stmt)).scalar_one_or_none()
            now = datetime.now(tz=UTC)
            if row is None:
                session.add(
                    RetentionPolicyModel(
                        table_name=table_name,
                        retention_days=retention_days,
                        last_pruned_at=None,
                        last_pruned_rows=0,
                        updated_at=now,
                    )
                )
            else:
                row.retention_days = retention_days
                row.updated_at = now
            await session.commit()

    async def update_retention(self, table_name: str, retention_days: int | None) -> None:
        async with self._sm() as session:
            stmt = select(RetentionPolicyModel).where(RetentionPolicyModel.table_name == table_name)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise UnknownPrunableTable(f"no retention policy registered for {table_name!r}")
            row.retention_days = retention_days
            row.updated_at = datetime.now(tz=UTC)
            await session.commit()

    async def touch_pruned(self, table_name: str, rows: int) -> None:
        async with self._sm() as session:
            stmt = select(RetentionPolicyModel).where(RetentionPolicyModel.table_name == table_name)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                raise UnknownPrunableTable(f"no retention policy registered for {table_name!r}")
            row.last_pruned_at = datetime.now(tz=UTC)
            row.last_pruned_rows = rows
            await session.commit()

    async def delete_older_than(
        self,
        table: str,
        timestamp_column: str,
        cutoff: datetime,
    ) -> int:
        allowed_columns = self._allowlist.get(table)
        if allowed_columns is None or timestamp_column not in allowed_columns:
            raise UnknownPrunableTable(
                f"table/column not in allowlist: ({table!r}, {timestamp_column!r})"
            )
        async with self._sm() as session:
            if table == "conversations":
                # A conversation owns its messages; pruning a thread must take
                # them with it (chat_messages has no DB-level cascade), so delete
                # the messages of the to-be-pruned threads first, in the same txn.
                await session.execute(
                    text(
                        "DELETE FROM chat_messages WHERE conversation_id IN "
                        f"(SELECT id FROM conversations WHERE {timestamp_column} < :cutoff)"
                    ),
                    {"cutoff": cutoff},
                )
            stmt = text(f"DELETE FROM {table} WHERE {timestamp_column} < :cutoff")
            result = await session.execute(stmt, {"cutoff": cutoff})
            await session.commit()
            return int(result.rowcount or 0)

    async def archive_older_than(
        self,
        target_table: str,
        match_column: str,
        set_column: str,
        cutoff: datetime,
        now: datetime,
    ) -> int:
        allowed_columns = self._allowlist.get(target_table)
        if (
            allowed_columns is None
            or match_column not in allowed_columns
            or set_column not in allowed_columns
        ):
            raise UnknownPrunableTable(
                f"table/columns not in allowlist: "
                f"({target_table!r}, {match_column!r}, {set_column!r})"
            )
        async with self._sm() as session:
            # Stamp only rows not already stamped, so a thread's original
            # archive time survives re-sweeps (and stays the delete clock).
            stmt = text(
                f"UPDATE {target_table} SET {set_column} = :now "
                f"WHERE {set_column} IS NULL AND {match_column} < :cutoff"
            )
            result = await session.execute(stmt, {"now": now, "cutoff": cutoff})
            await session.commit()
            return int(result.rowcount or 0)

    async def exists(self, table_name: str) -> bool:
        async with self._sm() as session:
            stmt = select(RetentionPolicyModel).where(RetentionPolicyModel.table_name == table_name)
            row = (await session.execute(stmt)).scalar_one_or_none()
            return row is not None
