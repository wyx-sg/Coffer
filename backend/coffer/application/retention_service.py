"""Retention policy orchestration service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from coffer.application.audit_service import AuditService
from coffer.application.repos import RetentionRepo
from coffer.application.retention_registry import (
    PrunableRegistry,
    PrunableTable,
    UnknownPrunableTable,
)
from coffer.domain.audit import AuditEventType


@dataclass(frozen=True)
class RetentionPolicyView:
    """Display-oriented merge of the registry's static info + the DB's runtime state."""

    table: PrunableTable
    retention_days: int | None
    last_pruned_at: datetime | None
    last_pruned_rows: int


class RetentionService:
    def __init__(
        self,
        registry: PrunableRegistry,
        repo: RetentionRepo,
        audit: AuditService,
    ) -> None:
        self._registry = registry
        self._repo = repo
        self._audit = audit

    async def initialize_defaults(self) -> None:
        """Seed missing retention rows from registry defaults.

        Idempotent — rows already in the DB are left alone (so user-set
        values survive daemon restarts).
        """
        for table in self._registry.all():
            if not await self._repo.exists(table.name):
                await self._repo.upsert(table.name, table.default_retention_days)

    async def list_policies(self) -> list[RetentionPolicyView]:
        result: list[RetentionPolicyView] = []
        for table in self._registry.all():
            try:
                policy = await self._repo.get(table.name)
            except UnknownPrunableTable:
                continue  # not yet seeded; should not happen after initialize_defaults
            result.append(
                RetentionPolicyView(
                    table=table,
                    retention_days=policy.retention_days,
                    last_pruned_at=policy.last_pruned_at,
                    last_pruned_rows=policy.last_pruned_rows,
                )
            )
        return result

    async def set_retention(self, table_name: str, days: int | None, actor: str) -> None:
        # Validate via registry FIRST; the registry's UnknownPrunableTable is
        # the user-facing error class.
        self._registry.get(table_name)
        if days is not None and days <= 0:
            raise ValueError(f"retention_days must be None or positive, got {days}")
        await self._repo.update_retention(table_name, days)
        await self._audit.record(
            AuditEventType.RETENTION_UPDATED.value,
            actor=actor,
            details={"table": table_name, "retention_days": days},
        )

    async def prune(
        self,
        table_name: str | None = None,
        *,
        now: datetime | None = None,
    ) -> dict[str, int]:
        """Run prune on one or all registered tables. Returns {table: rows_deleted}."""
        clock_now = now or datetime.now(tz=UTC)
        if table_name is not None:
            tables = [self._registry.get(table_name)]
        else:
            tables = self._registry.all()
        result: dict[str, int] = {}
        for table in tables:
            policy = await self._repo.get(table.name)
            if policy.retention_days is None:
                result[table.name] = 0
                continue
            cutoff = clock_now - timedelta(days=policy.retention_days)
            if table.action == "archive":
                assert table.archive_set_column is not None  # registry invariant
                affected = await self._repo.archive_older_than(
                    table.sql_table,
                    table.timestamp_column,
                    table.archive_set_column,
                    cutoff,
                    clock_now,
                )
            else:
                affected = await self._repo.delete_older_than(
                    table.sql_table, table.timestamp_column, cutoff
                )
            await self._repo.touch_pruned(table.name, affected)
            result[table.name] = affected
        return result
