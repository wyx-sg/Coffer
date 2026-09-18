"""0088 clears the reach of every ``knowledge`` and ``memory`` row.

The two kinds stop declaring reach, so a row still carrying a scope would hold
a permission no reader honours. This is the one revision in the tree that
WIDENS on purpose, which makes the interesting assertion the negative one: it
must widen exactly two kinds and leave the four that keep their reach
(``mcp_server`` / ``skill`` / ``provider`` / ``channel``) untouched, including
their dormant ``{"agents": []}`` rows — dormant is a real answer there, and
mistaking it for a value nobody chose would silently expose a resource its
owner had switched off.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migration_0079 import _seed
from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)


def _at_0087(tmp_path, monkeypatch, db_name: str):
    """A throwaway vault at the revision just below 0088."""
    db_path = tmp_path / db_name
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    (tmp_path / "daemon-config.json").write_text(
        json.dumps({"version": 1, "port": 8000, "machine_id": "b7a5160dc1ef128f"})
    )
    cfg = _alembic_config()
    command.upgrade(cfg, "0087")
    return db_path, cfg


def _set_scope(db_path: pathlib.Path, kind: str, name: str, scope: object) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE resources SET scope_json = ? WHERE kind = ? AND name = ?",
            (None if scope is None else json.dumps(scope), kind, name),
        )
        conn.commit()


def _scopes(db_path: pathlib.Path) -> dict[tuple[str, str], object]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT kind, name, scope_json FROM resources").fetchall()
    return {(kind, name): (None if raw is None else json.loads(raw)) for kind, name, raw in rows}


def test_0088_clears_knowledge_and_memory_and_nothing_else(tmp_path, monkeypatch):
    """The whole revision in one vault: two kinds emptied, four left alone.

    The ``memory`` scopes are the auto-defaults the aggregation pass really
    wrote — ``coffer`` scoped to Claude Code, ``account`` scoped to Codex — the
    pair that hid each partition from the other agent and motivated the
    withdrawal.
    """
    db_path, cfg = _at_0087(tmp_path, monkeypatch, "mixed.db")

    _seed(db_path, "knowledge", "shopee", {})
    _set_scope(db_path, "knowledge", "shopee", {"agents": ["claude-code"]})
    _seed(db_path, "memory", "coffer", {})
    _set_scope(db_path, "memory", "coffer", {"agents": ["claude-code"]})
    _seed(db_path, "memory", "account", {})
    _set_scope(db_path, "memory", "account", {"agents": ["codex"]})

    _seed(db_path, "mcp_server", "fs", {})
    _set_scope(db_path, "mcp_server", "fs", {"agents": ["codex"]})
    _seed(db_path, "skill", "reviewer", {})
    _set_scope(db_path, "skill", "reviewer", {"agents": ["claude-code"]})
    _seed(db_path, "provider", "ollama", {})
    _set_scope(db_path, "provider", "ollama", {"agents": []})
    _seed(db_path, "channel", "tg", {})
    _set_scope(db_path, "channel", "tg", {"agents": []})

    command.upgrade(cfg, "0088")

    assert _scopes(db_path) == {
        ("knowledge", "shopee"): None,
        ("memory", "coffer"): None,
        ("memory", "account"): None,
        # Dormant stays dormant for the kinds where dormant means something.
        ("mcp_server", "fs"): {"agents": ["codex"]},
        ("skill", "reviewer"): {"agents": ["claude-code"]},
        ("provider", "ollama"): {"agents": []},
        ("channel", "tg"): {"agents": []},
    }


def test_0088_is_idempotent_and_leaves_an_already_null_row_alone(tmp_path, monkeypatch):
    """Every real ``knowledge`` row was already ``NULL``, which is also the
    state the revision leaves behind — so running it twice must be a no-op the
    second time, and the first time must not disturb a row that needed nothing.
    """
    db_path, cfg = _at_0087(tmp_path, monkeypatch, "idem.db")
    _seed(db_path, "knowledge", "shopee", {})  # scope_json is NULL as registered
    _seed(db_path, "memory", "coffer", {})
    _set_scope(db_path, "memory", "coffer", {"agents": ["claude-code"]})

    command.upgrade(cfg, "0088")
    after_first = _scopes(db_path)

    command.downgrade(cfg, "0087")  # writes nothing — the values are unrecoverable
    command.upgrade(cfg, "0088")

    assert after_first == {("knowledge", "shopee"): None, ("memory", "coffer"): None}
    assert _scopes(db_path) == after_first


def test_0088_tolerates_a_scope_it_cannot_parse(tmp_path, monkeypatch):
    """A row's reach is cleared on its ``kind`` alone, never on its contents, so
    a fossil left by a retired axis upgrades as cleanly as a current one rather
    than failing the whole chain over a value nobody reads any more."""
    db_path, cfg = _at_0087(tmp_path, monkeypatch, "fossil.db")
    _seed(db_path, "memory", "coffer", {})
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE resources SET scope_json = 'not json' WHERE kind = 'memory'")
        conn.commit()

    command.upgrade(cfg, "0088")

    assert _scopes(db_path) == {("memory", "coffer"): None}
