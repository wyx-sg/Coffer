"""Revision 0061: agent rows stop carrying a wire_api Codex refuses to load.

``wire_api = "chat"`` makes Codex 0.139.0 fail to load ``config.toml`` outright,
so an agent projected with it has a CLI that will not start. ``AgentConfig`` now
rejects the value, which stops new ones; this revision fixes the rows written
while it was accepted — revision 0037 flipped the same value when it lived on
the CONNECTION, and 0040 moved the field onto the agent afterwards, so agent
rows were never covered.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts, like the 0048/0049/0050/0051/0056 tests do.
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


def test_0061_flips_the_dead_wire_and_leaves_everything_else(tmp_path, monkeypatch):
    """Only ``chat`` moves. A row already on ``responses``, one that never set
    the field, and a non-agent row are all untouched — and the rest of the
    flipped row's config survives the rewrite."""
    db_path = tmp_path / "wire_api.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0060")
    with sqlite3.connect(db_path) as conn:
        _seed(
            conn,
            "agent",
            "codex-dead",
            {
                "type": "codex",
                "config_dir": "/Users/x/.codex",
                "model": "gpt-5.4",
                "wire_api": "chat",
                "models": ["gpt-5.4"],
            },
        )
        _seed(conn, "agent", "codex-live", {"type": "codex", "wire_api": "responses"})
        _seed(conn, "agent", "claude", {"type": "claude_code", "model": "claude-opus-5"})
        _seed(conn, "provider", "acme", {"protocol": "openai", "wire_api": "chat"})

    command.upgrade(cfg, "0061")
    assert _alembic_version(db_path) == "0061"

    flipped = _config(db_path, "codex-dead")
    assert flipped["wire_api"] == "responses"
    # The flip rewrites the whole document, so assert it kept the rest.
    assert flipped["model"] == "gpt-5.4"
    assert flipped["models"] == ["gpt-5.4"]
    assert flipped["config_dir"] == "/Users/x/.codex"

    assert _config(db_path, "codex-live")["wire_api"] == "responses"
    assert "wire_api" not in _config(db_path, "claude")
    # Connections lost this field back in 0040; a row that somehow still carries
    # it is not this revision's business.
    assert _config(db_path, "acme", kind="provider")["wire_api"] == "chat"


def test_0061_downgrade_restores_the_previous_value(tmp_path, monkeypatch):
    """Down puts ``chat`` back on the rows that said it, and leaves a row that
    was already ``responses`` before the upgrade alone — the two are
    indistinguishable afterwards, which is why the downgrade is documented as
    restoring the data, not a working config."""
    db_path = tmp_path / "wire_api_down.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0060")
    with sqlite3.connect(db_path) as conn:
        _seed(conn, "agent", "codex-dead", {"type": "codex", "wire_api": "chat"})
        _seed(conn, "agent", "claude", {"type": "claude_code"})

    command.upgrade(cfg, "0061")
    command.downgrade(cfg, "0060")

    assert _alembic_version(db_path) == "0060"
    assert _config(db_path, "codex-dead")["wire_api"] == "chat"
    assert "wire_api" not in _config(db_path, "claude")


def test_0061_leaves_an_unparseable_row_alone(tmp_path, monkeypatch):
    """A config JSON the migration cannot read is not guessed at — it is left
    exactly as found, and the upgrade still completes for every other row."""
    db_path = tmp_path / "wire_api_bad.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0060")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
            "VALUES ('agent', 'broken', 'not json', 1, '2026-09-01', '2026-09-01')"
        )
        _seed(conn, "agent", "codex-dead", {"type": "codex", "wire_api": "chat"})

    command.upgrade(cfg, "0061")

    with sqlite3.connect(db_path) as conn:
        (raw,) = conn.execute("SELECT config_json FROM resources WHERE name = 'broken'").fetchone()
    assert raw == "not json"
    assert _config(db_path, "codex-dead")["wire_api"] == "responses"
