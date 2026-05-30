"""Genuine Alembic migration round-trip test.

Drives the real migration scripts against a throwaway SQLite file and asserts
the schema is created on ``upgrade head`` and fully torn down on
``downgrade base`` — i.e. proves the ``downgrade()`` functions actually run and
that the migration chain is reversible and idempotent.

``env.py`` reads ``COFFER_DB_URL`` (an async ``sqlite+aiosqlite://`` URL) and
runs migrations through the async engine, so the test sets that env var via
monkeypatch and lets ``env.py`` do the async/sync conversion itself.
"""

from __future__ import annotations

import pathlib
import sqlite3

from alembic import command
from alembic.config import Config as AlembicConfig

HEAD_REVISION = "0004"

# Tables that should exist once the full migration chain has been applied.
# The agent kind (spec 004-agent-registry) needs no table of its own — agents
# live in the generic `resources` table — so 0004 is the head revision.
EXPECTED_TABLES = {
    "resources",
    "audit_log",
    "retention_policies",
    "mcp_capability_preferences",
    "mcp_invocations",
    "mcp_server_health",
}

_ALEMBIC_INI = (
    pathlib.Path(__file__).resolve().parents[4]
    / "coffer"
    / "infrastructure"
    / "persistence"
    / "migrations"
    / "alembic.ini"
)


def _alembic_config() -> AlembicConfig:
    assert _ALEMBIC_INI.is_file(), f"alembic.ini not found at {_ALEMBIC_INI}"
    return AlembicConfig(str(_ALEMBIC_INI))


def _user_tables(db_path: pathlib.Path) -> set[str]:
    """Return the set of user-defined tables in the SQLite file.

    Excludes SQLite internal tables and Alembic's own bookkeeping table so the
    assertions speak only to schema owned by the migrations under test.
    """
    if not db_path.exists():
        return set()
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    finally:
        conn.close()
    return {name for (name,) in rows} - {"alembic_version"}


def _alembic_version(db_path: pathlib.Path) -> str | None:
    conn = sqlite3.connect(str(db_path))
    try:
        try:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        except sqlite3.OperationalError:
            return None
    finally:
        conn.close()
    return row[0] if row else None


def test_migration_roundtrip_is_reversible_and_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "roundtrip.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")

    cfg = _alembic_config()

    # 1. upgrade head -> full schema present, stamped at head.
    command.upgrade(cfg, "head")
    assert _user_tables(db_path) == EXPECTED_TABLES
    assert _alembic_version(db_path) == HEAD_REVISION

    # 2. downgrade base -> every downgrade() runs, all tables removed.
    command.downgrade(cfg, "base")
    assert _user_tables(db_path) == set()
    assert _alembic_version(db_path) is None

    # 3. upgrade head again -> round-trip is idempotent, schema restored.
    command.upgrade(cfg, "head")
    assert _user_tables(db_path) == EXPECTED_TABLES
    assert _alembic_version(db_path) == HEAD_REVISION


def test_migration_stepwise_downgrade_drops_per_revision_tables(tmp_path, monkeypatch):
    """Step the chain down one revision at a time and assert each downgrade()
    removes exactly the tables its matching upgrade() created."""
    db_path = tmp_path / "stepwise.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")

    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    assert _user_tables(db_path) == EXPECTED_TABLES

    # 0004 -> 0003: index-only revision, table set unchanged.
    command.downgrade(cfg, "0003")
    assert _user_tables(db_path) == EXPECTED_TABLES

    # 0003 -> 0002: drops mcp_server_health.
    command.downgrade(cfg, "0002")
    assert "mcp_server_health" not in _user_tables(db_path)

    # 0002 -> 0001: drops the mcp_* tables created in 0002.
    command.downgrade(cfg, "0001")
    tables = _user_tables(db_path)
    assert "mcp_capability_preferences" not in tables
    assert "mcp_invocations" not in tables
    assert {"resources", "audit_log", "retention_policies"} <= tables

    # 0001 -> base: everything gone.
    command.downgrade(cfg, "base")
    assert _user_tables(db_path) == set()
