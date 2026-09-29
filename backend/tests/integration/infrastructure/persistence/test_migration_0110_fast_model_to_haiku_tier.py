"""Revision 0110: an agent's ``fast_model`` becomes its Haiku tier pin.

Claude Code's background model is its Haiku tier; the deprecated
``ANTHROPIC_SMALL_FAST_MODEL`` the old field projected is gone, so the binding
moves into ``tier_models.haiku`` and the key is stripped from every agent row
(spec agent-registry "Carry the model binding on the agent record").
"""

from __future__ import annotations

import json
import sqlite3

import pytest
from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
    _alembic_version,
)


def _seed_agent(conn: sqlite3.Connection, uid: str, config: dict[str, object]) -> None:
    conn.execute(
        "INSERT INTO resources (uid, kind, name, config_json, enabled, created_at, updated_at)"
        " VALUES (?, 'agent', ?, ?, 1, '2026-09-30 00:00:00', '2026-09-30 00:00:00')",
        (uid, uid, json.dumps(config)),
    )


def _config(db_path, uid: str) -> dict[str, object]:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT config_json FROM resources WHERE uid = ?", (uid,)).fetchone()
    return json.loads(row[0])


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="an earlier fast model becomes the Haiku tier",
)
def test_0110_moves_fast_model_into_the_haiku_tier(tmp_path, monkeypatch):
    db_path = tmp_path / "tiers.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, "0109")
    with sqlite3.connect(db_path) as conn:
        _seed_agent(
            conn,
            "a" * 32,
            {"type": "claude_code", "model": "kimi-k3", "fast_model": "kimi-k3-mini"},
        )
        _seed_agent(conn, "c" * 32, {"type": "codex", "model": "gpt-x", "fast_model": None})

    command.upgrade(cfg, "0110")
    assert _alembic_version(db_path) == "0110"

    first = _config(db_path, "a" * 32)
    assert first == {
        "type": "claude_code",
        "model": "kimi-k3",
        "tier_models": {"haiku": "kimi-k3-mini"},
    }
    assert _config(db_path, "c" * 32) == {"type": "codex", "model": "gpt-x"}

    command.downgrade(cfg, "0109")
    assert _config(db_path, "a" * 32) == {
        "type": "claude_code",
        "model": "kimi-k3",
        "fast_model": "kimi-k3-mini",
    }


def test_0110_keeps_a_haiku_pin_already_there(tmp_path, monkeypatch):
    """A Haiku pin already there wins; the key goes regardless."""
    db_path = tmp_path / "pinned.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, "0109")
    with sqlite3.connect(db_path) as conn:
        _seed_agent(
            conn,
            "b" * 32,
            {"type": "claude_code", "fast_model": "small", "tier_models": {"haiku": "already"}},
        )
    command.upgrade(cfg, "0110")
    assert _config(db_path, "b" * 32) == {
        "type": "claude_code",
        "tier_models": {"haiku": "already"},
    }
