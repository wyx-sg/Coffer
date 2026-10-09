"""Retention policy orchestration service."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from coffer.application.audit_service import AuditService
from coffer.application.repos import RetentionRepo
from coffer.application.retention_registry import (
    FilePolicy,
    PrunableRegistry,
    UnknownPrunableTable,
)
from coffer.domain.audit import AuditEventType


@dataclass(frozen=True)
class RetentionPolicyView:
    """Display-oriented merge of a policy's static info + its stored runtime state.

    Carries the same fields for a table policy and a file policy.
    """

    name: str
    display_name: str
    description: str
    default_retention_days: int | None
    retention_days: int | None
    last_pruned_at: datetime | None
    last_pruned_rows: int


_logger = logging.getLogger(__name__)


class RetentionService:
    def __init__(
        self,
        registry: PrunableRegistry,
        repo: RetentionRepo,
        audit: AuditService,
        *,
        file_policies: Sequence[FilePolicy] = (),
    ) -> None:
        self._registry = registry
        self._repo = repo
        self._audit = audit
        # The file policies (attachments, skill working files): their directories
        # are not DB tables, so they ride the same cadence as file policies declared
        # at the composition root (spec resource-framework "Retain attachments on an
        # adjustable policy" and "Retain skill working files on an adjustable
        # policy"). Empty in tests that only exercise table prune.
        self._file_policies = {fp.name: fp for fp in file_policies}

    def _file_policy_named(self, name: str) -> FilePolicy | None:
        return self._file_policies.get(name)

    async def initialize_defaults(self) -> None:
        """Seed missing retention rows from registry defaults and forget the
        rows no registered policy owns any more (a retired policy leaves its
        row behind otherwise — the conversation archive/delete pair did).

        Idempotent — rows of live policies are left alone (so user-set
        values survive daemon restarts).
        """
        known = {t.name for t in self._registry.policies()} | set(self._file_policies)
        for stale in await self._repo.list():
            if stale.table_name not in known:
                await self._repo.remove(stale.table_name)
        for table in self._registry.policies():
            if not await self._repo.exists(table.name):
                await self._repo.upsert(table.name, table.default_retention_days)
        for fp in self._file_policies.values():
            if not await self._repo.exists(fp.name):
                await self._repo.upsert(fp.name, fp.default_retention_days)

    async def list_policies(self) -> list[RetentionPolicyView]:
        result: list[RetentionPolicyView] = []
        for table in self._registry.policies():
            try:
                policy = await self._repo.get(table.name)
            except UnknownPrunableTable:
                continue  # not yet seeded; should not happen after initialize_defaults
            result.append(
                RetentionPolicyView(
                    name=table.name,
                    display_name=table.display_name,
                    description=table.description,
                    default_retention_days=table.default_retention_days,
                    retention_days=policy.retention_days,
                    last_pruned_at=policy.last_pruned_at,
                    last_pruned_rows=policy.last_pruned_rows,
                )
            )
        for fp in self._file_policies.values():
            try:
                policy = await self._repo.get(fp.name)
            except UnknownPrunableTable:
                continue
            result.append(
                RetentionPolicyView(
                    name=fp.name,
                    display_name=fp.display_name,
                    description=fp.description,
                    default_retention_days=fp.default_retention_days,
                    retention_days=policy.retention_days,
                    last_pruned_at=policy.last_pruned_at,
                    last_pruned_rows=policy.last_pruned_rows,
                )
            )
        return result

    async def set_retention(self, table_name: str, days: int | None, actor: str) -> None:
        # Validate via registry FIRST; the registry's UnknownPrunableTable is
        # the user-facing error class.
        if self._file_policy_named(table_name) is None and not (
            self._registry.get(table_name).owns_policy
        ):
            # A follower has no window of its own to set; its leader's is it.
            raise UnknownPrunableTable(f"{table_name!r} follows another table's policy")
        if days is not None and days <= 0:
            raise ValueError(f"retention_days must be None or positive, got {days}")
        previous = (await self._repo.get(table_name)).retention_days
        await self._repo.update_retention(table_name, days)
        await self._audit.record(
            AuditEventType.RETENTION_UPDATED.value,
            actor=actor,
            # ``None`` on either side is "keep forever".
            details={"table": table_name, "retention_days": days, "previous_days": previous},
        )

    async def preview(
        self, table_name: str, days: int, *, now: datetime | None = None
    ) -> tuple[int, int]:
        """``(rows kept now, rows a window of ``days`` would delete)`` for one policy's own table
        (files, for a file policy).

        What the Settings Data tab asks before a shortening is confirmed; nothing is
        deleted. A follower has no window of its own, so it has no preview.
        """
        fp = self._file_policy_named(table_name)
        table = None if fp is not None else self._registry.get(table_name)
        if table is not None and not table.owns_policy:
            raise UnknownPrunableTable(f"{table_name!r} follows another table's policy")
        if days <= 0:
            raise ValueError(f"days must be positive, got {days}")
        if fp is not None:
            return fp.count(now or datetime.now(tz=UTC), days)
        assert table is not None
        cutoff = (now or datetime.now(tz=UTC)) - timedelta(days=days)
        return await self._repo.count_rows(
            table.sql_table,
            table.timestamp_column,
            cutoff,
        )

    async def prune(
        self,
        table_name: str | None = None,
        *,
        now: datetime | None = None,
    ) -> dict[str, int]:
        """Run prune on one or all registered tables. Returns {table: rows_deleted}."""
        clock_now = now or datetime.now(tz=UTC)
        named = self._file_policy_named(table_name) if table_name is not None else None
        if named is not None:
            # A single-policy request for a file policy sweeps only it.
            return {named.name: await self._sweep_files(named, clock_now)}
        if table_name is not None:
            target = self._registry.get(table_name)
            # Pruning a policy prunes the tables that follow it, too.
            tables = [target, *self._registry.followers(target.name)]
        else:
            tables = self._registry.all()
        result: dict[str, int] = {}
        for table in tables:
            policy = await self._repo.get(table.policy_key)
            if policy.retention_days is None:
                result[table.name] = 0
                continue
            cutoff = clock_now - timedelta(days=policy.retention_days)
            affected = await self._repo.delete_older_than(
                table.sql_table, table.timestamp_column, cutoff
            )
            if table.owns_policy:
                # A follower's rows are not its leader's: leave the leader's
                # "last pruned" count to the leader's own table.
                await self._repo.touch_pruned(table.name, affected)
            result[table.name] = affected
        if table_name is None:
            for fp in self._file_policies.values():
                result[fp.name] = await self._sweep_files(fp, clock_now)
        return result

    async def _sweep_files(self, fp: FilePolicy, now: datetime) -> int:
        """Run a file policy's sweeps with the stored window; 0 when kept forever.

        A failure in one sweep is logged and swallowed so a media-dir problem
        never breaks the DB prune or another policy's sweep.
        """
        policy = await self._repo.get(fp.name)
        if policy.retention_days is None:
            return 0
        deleted = 0
        for sweep in fp.sweeps:
            try:
                deleted += len(sweep(now, policy.retention_days))
            except Exception:
                _logger.exception("retention.media_sweep.failed", extra={"policy": fp.name})
        await self._repo.touch_pruned(fp.name, deleted)
        return deleted
