"""The retention SQL allowlist is derived from the registry, and only from it.

``delete_older_than`` interpolates a table and a column into SQL, so the set of
identifiers it accepts must come from code-level registrations only. The repo
takes that set as a required argument and keeps no list of its own, so a table
registered but not allowlisted (unsweepable) or allowlisted but not registered
(sweepable by nobody) cannot be expressed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.retention_registry import (
    PrunableRegistry,
    PrunableTable,
    UnknownPrunableTable,
)
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import create_async_engine_with_pragmas, session_maker
from coffer.infrastructure.persistence.retention_repo import (
    FileRetentionRepo,
    allowlist_from_registry,
)


def test_entries_sharing_a_table_merge_into_one_allowlist_entry() -> None:
    registry = PrunableRegistry()
    registry.register(
        PrunableTable(
            name="threads_by_update",
            timestamp_column="updated_at",
            default_retention_days=7,
            display_name="x",
            description="x",
            target_table="threads",
        )
    )
    registry.register(
        PrunableTable(
            name="threads",
            timestamp_column="created_at",
            default_retention_days=30,
            display_name="x",
            description="x",
        )
    )
    assert allowlist_from_registry(registry.all()) == {"threads": {"updated_at", "created_at"}}


async def _repo(tmp_path, allowlist):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return FileRetentionRepo(session_maker(engine), allowlist=allowlist), engine


@pytest.mark.asyncio
async def test_repo_sweeps_only_what_the_derived_allowlist_names(tmp_path) -> None:
    registry = PrunableRegistry()
    registry.register(
        PrunableTable(
            name="audit_log",
            timestamp_column="timestamp",
            default_retention_days=1,
            display_name="x",
            description="x",
        )
    )
    repo, engine = await _repo(tmp_path, allowlist_from_registry(registry.all()))
    try:
        cutoff = datetime.now(tz=UTC)
        assert await repo.delete_older_than("audit_log", "timestamp", cutoff) == 0
        # A real prunable table elsewhere in the app, but NOT in this
        # registry: refused, because this repo knows only what it was given.
        with pytest.raises(UnknownPrunableTable):
            await repo.delete_older_than("mcp_invocations", "timestamp", cutoff)
        # A column the registry never named on an allowed table: refused.
        with pytest.raises(UnknownPrunableTable):
            await repo.delete_older_than("audit_log", "actor", cutoff)
    finally:
        await engine.dispose()
