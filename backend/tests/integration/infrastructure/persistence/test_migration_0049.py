"""Revision 0049: scope collapses to an agent list, sync tables are dropped.

Continuous multi-machine sync is withdrawn (ADR-016 — export/import replaces
it) and the machine axis of ``scope`` goes with the machine registry that gave
machine ids meaning (ADR-045). This is the database half of that removal:

* every ``resources.scope_json`` value is rewritten from the old machine x
  agent mapping to a flat list of agent names (``null`` = every agent,
  ``[]`` = dormant);
* the ``kind='agent'`` / ``kind='channel'`` rows, whose kinds no longer declare
  any scope, are nulled out rather than collapsed — that also undoes 0047's
  ``runs_on -> scope`` backfill;
* the four sync-only tables (``sync_config``, ``sync_state``,
  ``machine_identity``, ``sync_tombstones``) are dropped.

Reuses the alembic driving helpers from the round-trip suite so both tests
speak to the same real migration scripts and the same ``COFFER_DB_URL`` wiring.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
    _alembic_version,
    _user_tables,
)

# Tables 0049 drops. Inlined exactly as the migration inlines them: no
# application model names them any more, so the test cannot import them.
DROPPED_TABLES = {"sync_config", "sync_state", "machine_identity", "sync_tombstones"}

# A machine id looked like this (a ULID minted by the withdrawn registry).
MACHINE_A = "01J0000000000000000000000A"
MACHINE_B = "01J0000000000000000000000B"


def _seed(conn: sqlite3.Connection, kind: str, name: str, scope: object) -> None:
    """Insert one resource row carrying a pre-0049 ``scope_json`` value."""
    conn.execute(
        "INSERT INTO resources "
        "(kind, name, config_json, scope_json, enabled, created_at, updated_at) "
        "VALUES (?, ?, '{}', ?, 1, '2026-09-01', '2026-09-01')",
        (kind, name, None if scope is None else json.dumps(scope)),
    )


def _scopes(db_path: pathlib.Path) -> dict[str, object]:
    with sqlite3.connect(db_path) as conn:
        return {
            name: (json.loads(raw) if raw is not None else None)
            for name, raw in conn.execute("SELECT name, scope_json FROM resources").fetchall()
        }


def test_0049_collapses_machine_agent_scope_to_an_agent_list(tmp_path, monkeypatch):
    """The machine axis is folded away: values union into one agent list, a
    ``"*"`` anywhere becomes NULL (active for every agent), an empty mapping
    stays dormant (``[]``) and NULL stays NULL."""
    db_path = tmp_path / "collapse_scope.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0048")
    with sqlite3.connect(db_path) as conn:
        _seed(conn, "mcp_server", "one-machine", {MACHINE_A: ["claude-code", "codex"]})
        _seed(conn, "skill", "two-machines", {MACHINE_A: ["claude-code"], MACHINE_B: ["codex"]})
        _seed(conn, "mcp_server", "machine-wildcard", {MACHINE_A: "*"})
        _seed(conn, "skill", "every-machine", {"*": "*"})
        _seed(conn, "mcp_server", "dormant", {})
        _seed(conn, "skill", "unscoped", None)
        _seed(conn, "mcp_server", "empty-agent-list", {MACHINE_A: []})
        conn.commit()

    command.upgrade(cfg, "0049")
    assert _alembic_version(db_path) == "0049"

    scopes = _scopes(db_path)
    assert scopes["one-machine"] == ["claude-code", "codex"]
    # Union across machines, in a stable (sorted) order.
    assert scopes["two-machines"] == ["claude-code", "codex"]
    assert scopes["machine-wildcard"] is None  # every agent
    assert scopes["every-machine"] is None  # every agent
    assert scopes["dormant"] == []  # active for no agent
    assert scopes["unscoped"] is None  # untouched
    assert scopes["empty-agent-list"] == []


def test_0049_unions_overlapping_agents_without_duplicates(tmp_path, monkeypatch):
    """Two machines naming the same agent collapse to one entry."""
    db_path = tmp_path / "union_scope.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0048")
    with sqlite3.connect(db_path) as conn:
        _seed(
            conn,
            "skill",
            "overlap",
            {MACHINE_A: ["codex", "claude-code"], MACHINE_B: ["codex"]},
        )
        conn.commit()

    command.upgrade(cfg, "0049")
    assert _scopes(db_path)["overlap"] == ["claude-code", "codex"]


def test_0049_nulls_scope_for_kinds_that_no_longer_carry_it(tmp_path, monkeypatch):
    """``agent`` and ``channel`` declare no scope now (ADR-045), so their stored
    mapping is cleared rather than collapsed — leaving a dict behind would make
    ``agent_in_scope`` test membership against a mapping's keys. This also
    undoes 0047's channel ``runs_on -> scope`` backfill."""
    db_path = tmp_path / "clear_scope.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0048")
    with sqlite3.connect(db_path) as conn:
        _seed(conn, "agent", "bound-agent", {MACHINE_A: "*"})
        _seed(conn, "channel", "bound-channel", {MACHINE_A: "*"})
        _seed(conn, "channel", "dormant-channel", {})  # 0047's unbound backfill
        _seed(conn, "channel", "already-null", None)
        conn.commit()

    command.upgrade(cfg, "0049")

    scopes = _scopes(db_path)
    assert scopes["bound-agent"] is None
    assert scopes["bound-channel"] is None
    assert scopes["dormant-channel"] is None  # NOT [] — a channel runs where enabled
    assert scopes["already-null"] is None


def test_0049_drops_the_sync_only_tables(tmp_path, monkeypatch):
    """The four tables that only existed for continuous sync are gone at head."""
    db_path = tmp_path / "drop_sync_tables.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0048")
    assert _user_tables(db_path) >= DROPPED_TABLES

    command.upgrade(cfg, "0049")
    assert not (DROPPED_TABLES & _user_tables(db_path))


def test_0049_drop_survives_a_database_already_missing_a_table(tmp_path, monkeypatch):
    """Guarded per table: a DB that somehow lacks one still upgrades."""
    db_path = tmp_path / "partial_tables.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0048")
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE sync_tombstones")
        conn.execute("DROP TABLE machine_identity")
        conn.commit()

    command.upgrade(cfg, "0049")
    assert _alembic_version(db_path) == "0049"
    assert not (DROPPED_TABLES & _user_tables(db_path))


def test_0049_is_idempotent(tmp_path, monkeypatch):
    """A fresh install upgrades cleanly, and re-running 0049 changes nothing."""
    db_path = tmp_path / "idempotent.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "head")
    assert _alembic_version(db_path) == "0049"
    assert not (DROPPED_TABLES & _user_tables(db_path))

    with sqlite3.connect(db_path) as conn:
        _seed(conn, "mcp_server", "already-collapsed", ["claude-code"])
        _seed(conn, "skill", "already-null", None)
        _seed(conn, "mcp_server", "already-dormant", [])
        conn.commit()
    before = _scopes(db_path)

    # Re-run the upgrade step over the same DB: the collapse is a no-op on
    # values that are already lists, and the tables are already gone.
    command.stamp(cfg, "0048")
    command.upgrade(cfg, "0049")
    assert _scopes(db_path) == before
    assert not (DROPPED_TABLES & _user_tables(db_path))


def test_0049_downgrade_restores_the_tables_so_the_chain_keeps_running(tmp_path, monkeypatch):
    """The collapse is one-way (machine keys are unrecoverable), but the dropped
    tables come back empty on the way down — 0019/0042/0043's own downgrades
    drop them again, and 0044/0045 need their columns to exist."""
    db_path = tmp_path / "downgrade.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "head")
    with sqlite3.connect(db_path) as conn:
        _seed(conn, "mcp_server", "collapsed", ["claude-code"])
        conn.commit()

    command.downgrade(cfg, "0048")
    assert _user_tables(db_path) >= DROPPED_TABLES

    def _columns(table: str) -> set[str]:
        with sqlite3.connect(db_path) as conn:
            return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}

    # Columns added by 0043/0044/0045 must be there for their downgrades.
    assert {"quarantined_refs_json", "failed_state_json"} <= _columns("sync_state")
    assert "poll_remote_seconds" in _columns("sync_config")

    # Scope is NOT reconstructed — the machine keys are gone for good.
    assert _scopes(db_path)["collapsed"] == ["claude-code"]

    # And back up again: the restored tables are dropped a second time.
    command.upgrade(cfg, "head")
    assert not (DROPPED_TABLES & _user_tables(db_path))
