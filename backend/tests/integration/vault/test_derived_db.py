"""``derived/derived.db`` is rebuilt, never migrated."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from coffer.infrastructure.mcp.health_repo import MCPServerHealthRepo
from coffer.infrastructure.persistence.derived_db import (
    SCHEMA_VERSION,
    derived_db_path,
    open_derived_db,
)


async def test_a_file_at_another_schema_version_is_recreated() -> None:
    engine, sm = await open_derived_db()
    await MCPServerHealthRepo(sm).upsert("u1", "healthy", datetime.now(tz=UTC))
    await engine.dispose()
    path = derived_db_path()
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    engine, sm = await open_derived_db()
    try:
        assert await MCPServerHealthRepo(sm).list_all() == []
    finally:
        await engine.dispose()


async def test_a_failing_row_keeps_why_it_failed() -> None:
    engine, sm = await open_derived_db()
    try:
        repo = MCPServerHealthRepo(sm)
        await repo.upsert("u1", "failing", datetime.now(tz=UTC), "auth_rejected")
        assert await repo.get_reason("u1") == "auth_rejected"
        await repo.upsert("u1", "healthy", datetime.now(tz=UTC))
        assert await repo.get_reason("u1") is None
        assert await repo.get_reason("absent") is None
    finally:
        await engine.dispose()


async def test_the_same_version_keeps_its_rows() -> None:
    engine, sm = await open_derived_db()
    await MCPServerHealthRepo(sm).upsert("u1", "failing", datetime.now(tz=UTC))
    await engine.dispose()
    engine, sm = await open_derived_db()
    try:
        assert await MCPServerHealthRepo(sm).list_all() == [("u1", "failing")]
    finally:
        await engine.dispose()
