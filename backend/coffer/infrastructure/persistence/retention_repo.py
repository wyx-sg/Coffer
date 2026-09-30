"""RetentionRepo — the policies in ``local/retention.json``, the sweep in SQL.

A retention policy is a setting of this machine (how long *its* history is
kept), so it is local state (ADR storage-is-five-classes-by-nature; plan D10):
one JSON object ``{table: {retention_days, last_pruned_at, last_pruned_rows,
updated_at}}`` written atomically. What a policy prunes is history, so the
sweep itself stays SQL against ``runs.db``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.application.retention_registry import PrunableTable, UnknownPrunableTable
from coffer.domain.retention import RetentionPolicy
from coffer.infrastructure.vault.home import local_root
from coffer.infrastructure.vault.json_store import JsonStore


def retention_path() -> Path:
    return local_root() / "retention.json"


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


def _time(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _to_domain(table_name: str, raw: dict[str, Any]) -> RetentionPolicy:
    days = raw.get("retention_days")
    rows = raw.get("last_pruned_rows")
    return RetentionPolicy(
        table_name=table_name,
        retention_days=days if isinstance(days, int) and not isinstance(days, bool) else None,
        last_pruned_at=_time(raw.get("last_pruned_at")),
        last_pruned_rows=rows if isinstance(rows, int) else 0,
        updated_at=_time(raw.get("updated_at")) or datetime.now(tz=UTC),
    )


class FileRetentionRepo:
    """Concrete RetentionRepo: policies in ``local/retention.json``, the sweep
    against the history database.

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
        path: Path | Callable[[], Path] = retention_path,
    ) -> None:
        self._sm = sm
        self._allowlist: Mapping[str, set[str]] = allowlist
        self._store = JsonStore(path)

    def _policies(self) -> dict[str, Any]:
        return {k: v for k, v in self._store.read().items() if isinstance(v, dict)}

    async def get(self, table_name: str) -> RetentionPolicy:
        raw = self._policies().get(table_name)
        if raw is None:
            raise UnknownPrunableTable(f"no retention policy registered for {table_name!r}")
        return _to_domain(table_name, raw)

    async def list(self) -> list[RetentionPolicy]:
        return [_to_domain(name, raw) for name, raw in sorted(self._policies().items())]

    async def upsert(self, table_name: str, retention_days: int | None) -> None:
        now = datetime.now(tz=UTC).isoformat()

        def change(doc: dict[str, Any]) -> None:
            row = doc.get(table_name)
            if not isinstance(row, dict):
                row = {"last_pruned_at": None, "last_pruned_rows": 0}
                doc[table_name] = row
            row["retention_days"] = retention_days
            row["updated_at"] = now

        self._store.update(change)

    def _change_existing(self, table_name: str, fields: dict[str, Any]) -> None:
        def change(doc: dict[str, Any]) -> None:
            row = doc.get(table_name)
            if not isinstance(row, dict):
                raise UnknownPrunableTable(f"no retention policy registered for {table_name!r}")
            row.update(fields)

        self._store.update(change)

    async def update_retention(self, table_name: str, retention_days: int | None) -> None:
        self._change_existing(
            table_name,
            {"retention_days": retention_days, "updated_at": datetime.now(tz=UTC).isoformat()},
        )

    async def touch_pruned(self, table_name: str, rows: int) -> None:
        self._change_existing(
            table_name,
            {"last_pruned_at": datetime.now(tz=UTC).isoformat(), "last_pruned_rows": rows},
        )

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

    async def count_rows(
        self,
        table: str,
        timestamp_column: str,
        cutoff: datetime,
    ) -> tuple[int, int]:
        """``(all rows, rows older than cutoff)``: what a prune at ``cutoff`` would delete."""
        allowed_columns = self._allowlist.get(table)
        if allowed_columns is None or timestamp_column not in allowed_columns:
            raise UnknownPrunableTable(
                f"table/column not in allowlist: ({table!r}, {timestamp_column!r})"
            )
        async with self._sm() as session:
            stmt = text(
                f"SELECT COUNT(*), COALESCE(SUM(CASE WHEN {timestamp_column} < :cutoff "
                f"THEN 1 ELSE 0 END), 0) FROM {table}"
            )
            total, older = (await session.execute(stmt, {"cutoff": cutoff})).one()
            return int(total or 0), int(older or 0)

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
        return table_name in self._policies()


__all__ = ["FileRetentionRepo", "allowlist_from_registry", "retention_path"]
