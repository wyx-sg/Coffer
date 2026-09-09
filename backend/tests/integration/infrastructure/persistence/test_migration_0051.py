"""Revision 0051: removed agent types leave connections' ``compatible_agents``.

0048 deleted the ``kind='agent'`` rows for the four removed types but not the
same names inside ``kind='provider'`` rows, where ``compatible_agents`` lists
the agent types a connection may project into. ``ProviderConfig`` forbids them,
so the first ``model_validate`` after the upgrade raises and a working
connection becomes unreadable — taking the LLM-connections page and the Codex
key lookup with it. Found on a live install whose ACTIVE connection carried
``["codex", "opencode", "hermes", "openclaw", "claude_code"]``.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts, like the 0048/0049/0050 tests do.
"""

from __future__ import annotations

import json
import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
    _alembic_version,
)

# Inlined exactly as the migration inlines them: these values are no longer in
# ``AgentType``, so the test cannot (and must not) import them.
REMOVED_TYPES = ("cursor", "opencode", "openclaw", "hermes")


def _seed_provider(conn: sqlite3.Connection, name: str, compatible: object) -> None:
    config: dict[str, object] = {
        "protocol": "openai",
        "base_url": "https://gateway.example/v1",
        "credential_ref": f"{name}-key",
        "is_active": True,
    }
    if compatible is not ...:
        config["compatible_agents"] = compatible
    conn.execute(
        "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
        "VALUES ('provider', ?, ?, 1, '2026-09-01', '2026-09-01')",
        (name, json.dumps(config)),
    )


def _compatible(db_path, name: str) -> object:
    with sqlite3.connect(db_path) as conn:
        (raw,) = conn.execute(
            "SELECT config_json FROM resources WHERE kind = 'provider' AND name = ?", (name,)
        ).fetchone()
    return json.loads(raw).get("compatible_agents", ...)


def test_0051_drops_removed_types_and_keeps_the_rest(tmp_path, monkeypatch):
    """The live shape: a connection routed to several agents, only two of which
    still exist. The survivors stay, in order."""
    db_path = tmp_path / "narrow_compatible.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0050")
    with sqlite3.connect(db_path) as conn:
        _seed_provider(conn, "agnes", ["codex", "opencode", "hermes", "openclaw", "claude_code"])
        conn.commit()

    command.upgrade(cfg, "0051")
    assert _alembic_version(db_path) == "0051"

    assert _compatible(db_path, "agnes") == ["codex", "claude_code"]


def test_0051_falls_back_to_the_wire_default_when_nothing_survives(tmp_path, monkeypatch):
    """An empty list would project into no agent at all; null means "the default
    for this wire", the state the row would have had un-narrowed."""
    db_path = tmp_path / "all_removed.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0050")
    with sqlite3.connect(db_path) as conn:
        _seed_provider(conn, "only-removed", list(REMOVED_TYPES))
        conn.commit()

    command.upgrade(cfg, "0051")

    assert _compatible(db_path, "only-removed") is None


def test_0051_leaves_clean_and_absent_values_untouched(tmp_path, monkeypatch):
    """Idempotent, and it must not invent a value for a row that never had one."""
    db_path = tmp_path / "clean.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0050")
    with sqlite3.connect(db_path) as conn:
        _seed_provider(conn, "kept", ["claude_code"])
        _seed_provider(conn, "wire-default", ...)  # no compatible_agents key at all
        _seed_provider(conn, "explicit-null", None)
        conn.commit()

    command.upgrade(cfg, "0051")

    assert _compatible(db_path, "kept") == ["claude_code"]
    assert _compatible(db_path, "wire-default") is ...
    assert _compatible(db_path, "explicit-null") is None
