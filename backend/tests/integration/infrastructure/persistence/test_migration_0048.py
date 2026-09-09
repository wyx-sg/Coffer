"""Revision 0048 data migration: agent types narrowed to claude_code + codex.

Agents live in the generic ``resources`` table as ``kind='agent'`` rows whose
``config_json`` carries ``"type": "<agent_type>"``. Once ``AgentType`` loses the
``cursor`` / ``opencode`` / ``openclaw`` / ``hermes`` members, any stored row
still carrying one makes ``AgentConfig.model_validate`` raise, which would 500
every agent listing — so 0048 deletes those rows.

Unlike the earlier 0031 (which cut the same four types back when they had never
shipped), these agents were really delivered, so a real install can hold such
rows. 0048 owns the database only: files Coffer wrote into those agents' config
directories are deliberately left on disk (the daemon names them once at
startup, see ``test_removed_agent_leftovers``).

Reuses the alembic driving helpers from the round-trip suite so both tests
speak to the same real migration scripts and the same ``COFFER_DB_URL`` wiring.
"""

from __future__ import annotations

import json
import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    HEAD_REVISION,
    _alembic_config,
    _alembic_version,
)

# Inlined on purpose, exactly as the migration inlines them: these values are no
# longer in the ``AgentType`` enum, so the test cannot (and must not) import them.
REMOVED_TYPES = ("cursor", "opencode", "openclaw", "hermes")


def _seed_agent(conn: sqlite3.Connection, name: str, agent_type: str) -> None:
    conn.execute(
        "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
        "VALUES ('agent', ?, ?, 1, '2026-09-01', '2026-09-01')",
        (name, json.dumps({"type": agent_type, "config_dir": f"/tmp/{agent_type}"})),
    )


def _agent_names(db_path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {r[0] for r in conn.execute("SELECT name FROM resources WHERE kind = 'agent'")}


def test_0048_deletes_removed_agent_type_rows(tmp_path, monkeypatch):
    """Rows for the four removed types are DELETED; kept-type rows survive."""
    db_path = tmp_path / "narrow_agent_types.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    # Stop one revision BEFORE 0048 and seed rows for removed + kept types.
    command.upgrade(cfg, "0047")
    with sqlite3.connect(db_path) as conn:
        for agent_type in REMOVED_TYPES:
            _seed_agent(conn, f"a-{agent_type}", agent_type)
        _seed_agent(conn, "a-claude", "claude_code")
        conn.commit()
    assert _agent_names(db_path) == {
        "a-cursor",
        "a-opencode",
        "a-openclaw",
        "a-hermes",
        "a-claude",
    }

    command.upgrade(cfg, "0048")
    assert _alembic_version(db_path) == "0048"

    assert _agent_names(db_path) == {"a-claude"}


def test_0048_leaves_a_config_dir_only_row_alone_when_type_is_kept(tmp_path, monkeypatch):
    """The delete keys off the stored ``type``, never off the config directory."""
    db_path = tmp_path / "kept_types.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0047")
    with sqlite3.connect(db_path) as conn:
        # A kept-type agent that happens to live under a removed agent's dir.
        conn.execute(
            "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
            "VALUES ('agent', 'a-codex', ?, 1, '2026-09-01', '2026-09-01')",
            (json.dumps({"type": "codex", "config_dir": "/tmp/opencode"}),),
        )
        # A non-agent row whose config_json mentions a removed type must survive.
        conn.execute(
            "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
            "VALUES ('skill', 's-1', ?, 1, '2026-09-01', '2026-09-01')",
            (json.dumps({"type": "opencode"}),),
        )
        conn.commit()

    command.upgrade(cfg, "0048")

    assert _agent_names(db_path) == {"a-codex"}
    with sqlite3.connect(db_path) as conn:
        (skills,) = conn.execute("SELECT COUNT(*) FROM resources WHERE kind = 'skill'").fetchone()
    assert skills == 1


def test_0048_is_a_no_op_on_a_database_without_removed_rows(tmp_path, monkeypatch):
    """Idempotent: nothing to delete on a fresh install, and re-running is safe."""
    db_path = tmp_path / "no_op.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    # A fresh install upgraded straight to head has no removed-type rows at all.
    command.upgrade(cfg, "head")
    assert _alembic_version(db_path) == HEAD_REVISION
    assert _agent_names(db_path) == set()

    # Re-running the whole chain (down to before 0048 and back up) stays a no-op
    # and does not touch the kept-type row seeded in between.
    with sqlite3.connect(db_path) as conn:
        _seed_agent(conn, "a-claude", "claude_code")
        conn.commit()
    command.downgrade(cfg, "0047")
    command.upgrade(cfg, "head")
    assert _alembic_version(db_path) == HEAD_REVISION
    assert _agent_names(db_path) == {"a-claude"}
