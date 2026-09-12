"""Revision 0063: the curated ``models`` set comes back OFF every agent.

Model curation moved from the agent to the channel (spec channels FR-071), so
0060's per-agent ticked set has no reader left — and ``AgentConfig`` forbids
extra keys, which means a row that kept it would fail to validate on load. This
is the whole of the cleanup: there is no load-time shim tolerating the key.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts, like the 0048/0049/0050/0051/0056/0061 tests do.
"""

from __future__ import annotations

import json
import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
    _alembic_version,
)


def _seed(conn: sqlite3.Connection, kind: str, name: str, config: dict[str, object]) -> None:
    conn.execute(
        "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
        "VALUES (?, ?, ?, 1, '2026-09-01', '2026-09-01')",
        (kind, name, json.dumps(config)),
    )


def _config(db_path, name: str, kind: str = "agent") -> dict[str, object]:
    with sqlite3.connect(db_path) as conn:
        (raw,) = conn.execute(
            "SELECT config_json FROM resources WHERE kind = ? AND name = ?", (kind, name)
        ).fetchone()
    return json.loads(raw)


def test_0063_strips_the_key_and_leaves_everything_else(tmp_path, monkeypatch):
    """Every agent row loses ``models``, curated or not, and keeps the rest of
    its config. A CONNECTION's own curated set (0059) is a different field on a
    different kind and stays exactly where it is."""
    db_path = tmp_path / "agent_models.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0062")
    with sqlite3.connect(db_path) as conn:
        _seed(
            conn,
            "agent",
            "claude",
            {
                "type": "claude_code",
                "config_dir": "/Users/x/.claude",
                "model": "claude-opus-5",
                "models": ["claude-opus-5", "claude-haiku-4-5"],
            },
        )
        _seed(conn, "agent", "codex", {"type": "codex", "models": []})
        _seed(conn, "provider", "acme", {"protocol": "openai", "models": ["gpt-5"]})

    command.upgrade(cfg, "0063")
    assert _alembic_version(db_path) == "0063"

    curated = _config(db_path, "claude")
    assert "models" not in curated
    # The strip rewrites the whole document, so assert it kept the rest.
    assert curated["model"] == "claude-opus-5"
    assert curated["config_dir"] == "/Users/x/.claude"

    assert "models" not in _config(db_path, "codex")
    # A connection's curated set is not this revision's business.
    assert _config(db_path, "acme", kind="provider")["models"] == ["gpt-5"]


def test_0063_downgrade_restores_the_uncurated_default(tmp_path, monkeypatch):
    """Down puts the key back as ``[]`` — 0060's "not curated, offer
    everything". Which models were ticked is not recoverable and nothing above
    reads them any more, so there was nothing to preserve."""
    db_path = tmp_path / "agent_models_down.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0062")
    with sqlite3.connect(db_path) as conn:
        _seed(conn, "agent", "claude", {"type": "claude_code", "models": ["claude-opus-5"]})

    command.upgrade(cfg, "0063")
    command.downgrade(cfg, "0062")

    assert _alembic_version(db_path) == "0062"
    assert _config(db_path, "claude")["models"] == []


def test_0063_leaves_an_unparseable_row_alone(tmp_path, monkeypatch):
    """A config JSON the migration cannot read is not guessed at — it is left
    exactly as found, and the upgrade still completes for every other row."""
    db_path = tmp_path / "agent_models_bad.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0062")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
            "VALUES ('agent', 'broken', 'not json', 1, '2026-09-01', '2026-09-01')"
        )
        _seed(conn, "agent", "claude", {"type": "claude_code", "models": ["claude-opus-5"]})

    command.upgrade(cfg, "0063")

    with sqlite3.connect(db_path) as conn:
        (raw,) = conn.execute("SELECT config_json FROM resources WHERE name = 'broken'").fetchone()
    assert raw == "not json"
    assert "models" not in _config(db_path, "claude")
