"""The retention SQL allowlist is derived from the registry, not kept by hand.

``delete_older_than`` interpolates a table and a column into SQL, so the set of
identifiers it accepts must come from code-level registrations only. Deriving
the allowlist from the same ``PrunableTable`` entries the composition root
registers keeps the two from drifting: a table registered but not allowlisted
(unsweepable) or allowlisted but not registered (sweepable by nobody) can no
longer happen.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from coffer.application.retention_registry import PrunableRegistry, PrunableTable
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import create_async_engine_with_pragmas, session_maker
from coffer.infrastructure.persistence.retention import UnknownPrunableTable
from coffer.infrastructure.persistence.retention_repo import (
    _PRUNABLE_TABLE_ALLOWLIST,
    SqlAlchemyRetentionRepo,
    allowlist_from_registry,
)
from coffer.surfaces.http.app_mcp_composition import build_prunable_registry


def test_composition_registry_derives_exactly_the_static_allowlist() -> None:
    """The static default and the live derivation must agree — this is the
    startup-time equality the daemon used to leave to code review."""
    derived = allowlist_from_registry(build_prunable_registry().all())
    assert derived == _PRUNABLE_TABLE_ALLOWLIST


def test_archive_entry_permits_both_its_columns_on_the_target_table() -> None:
    registry = PrunableRegistry()
    registry.register(
        PrunableTable(
            name="threads_archive",
            timestamp_column="updated_at",
            default_retention_days=7,
            display_name="x",
            description="x",
            action="archive",
            target_table="threads",
            archive_set_column="archived_at",
        )
    )
    registry.register(
        PrunableTable(
            name="threads",
            timestamp_column="archived_at",
            default_retention_days=30,
            display_name="x",
            description="x",
        )
    )
    assert allowlist_from_registry(registry.all()) == {"threads": {"updated_at", "archived_at"}}


async def _repo(tmp_path, allowlist):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return SqlAlchemyRetentionRepo(session_maker(engine), allowlist=allowlist), engine


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
        # Registered in the static default, but NOT in this registry: refused.
        with pytest.raises(UnknownPrunableTable):
            await repo.delete_older_than("mcp_invocations", "timestamp", cutoff)
        # A column the registry never named on an allowed table: refused.
        with pytest.raises(UnknownPrunableTable):
            await repo.delete_older_than("audit_log", "actor", cutoff)
    finally:
        await engine.dispose()
