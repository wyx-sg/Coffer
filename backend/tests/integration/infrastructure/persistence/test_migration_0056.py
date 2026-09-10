"""Revision 0056: agent rows keep config keys the model no longer declares.

#323 dropped ``disable_native_memory`` from ``AgentConfig``, and the
``auto_detected`` flag went earlier still, but neither was ever stripped from
the rows written while they existed. ``AgentConfig`` is ``extra="forbid"``, so
the first ``model_validate`` after the upgrade raises and
``GET /api/v1/agents`` answers 422 — the whole Agents page goes down. Found on
a live install whose two registered agents both carried
``"disable_native_memory": false``.

The load-time tolerance that used to paper over this is deleted with this
revision: a migration fixes the data once, at rest, and then it is done.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts, like the 0048/0049/0050/0051 tests do.
"""

from __future__ import annotations

import json
import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
    _alembic_version,
)


def _seed_agent(conn: sqlite3.Connection, name: str, config: dict[str, object]) -> None:
    conn.execute(
        "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
        "VALUES ('agent', ?, ?, 1, '2026-09-01', '2026-09-01')",
        (name, json.dumps(config)),
    )


def _config(db_path, name: str, kind: str = "agent") -> dict[str, object]:
    with sqlite3.connect(db_path) as conn:
        (raw,) = conn.execute(
            "SELECT config_json FROM resources WHERE kind = ? AND name = ?", (kind, name)
        ).fetchone()
    return json.loads(raw)


def test_0056_strips_dead_keys_and_keeps_the_rest(tmp_path, monkeypatch):
    """The live shape: both dead keys go, every field the model still declares
    survives untouched."""
    db_path = tmp_path / "strip_dead_keys.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0055")
    with sqlite3.connect(db_path) as conn:
        _seed_agent(
            conn,
            "claude-code",
            {
                "type": "claude_code",
                "config_dir": "/Users/someone/.claude",
                "follow_all_skills": True,
                "skill_exclusions": ["frontend-slides"],
                "disable_native_memory": False,
                "auto_detected": True,
                "model": "claude-opus-5",
                "fast_model": None,
                "wire_api": None,
            },
        )
        conn.commit()

    command.upgrade(cfg, "0056")
    assert _alembic_version(db_path) == "0056"

    assert _config(db_path, "claude-code") == {
        "type": "claude_code",
        "config_dir": "/Users/someone/.claude",
        "follow_all_skills": True,
        "skill_exclusions": ["frontend-slides"],
        "model": "claude-opus-5",
        "fast_model": None,
        "wire_api": None,
    }


def test_0056_leaves_clean_rows_and_other_kinds_alone(tmp_path, monkeypatch):
    """A row written after #323 never had the keys; the migration must not
    rewrite it, nor touch any other kind's config."""
    db_path = tmp_path / "already_clean.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0055")
    clean = {"type": "codex", "config_dir": None, "follow_all_skills": True}
    with sqlite3.connect(db_path) as conn:
        _seed_agent(conn, "codex", clean)
        conn.execute(
            "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
            "VALUES ('skill', 'verify', ?, 1, '2026-09-01', '2026-09-01')",
            (json.dumps({"source": "local_import", "disable_native_memory": True}),),
        )
        conn.commit()

    command.upgrade(cfg, "0056")

    assert _config(db_path, "codex") == clean
    # Only kind='agent' is this migration's business.
    assert _config(db_path, "verify", kind="skill")["disable_native_memory"] is True


def test_0056_downgrade_leaves_the_rows_stripped(tmp_path, monkeypatch):
    """Downgrading must NOT put the keys back. One revision down is 0055, whose
    code is main-as-of-#333 — long after #323 removed the fields — so a restored
    `disable_native_memory` is exactly the row that build cannot load. Putting it
    back would re-create the 422 this revision exists to end."""
    db_path = tmp_path / "downgrade.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0056")
    stripped = {"type": "codex", "follow_all_skills": True}
    with sqlite3.connect(db_path) as conn:
        _seed_agent(conn, "codex", stripped)
        conn.commit()

    command.downgrade(cfg, "0055")

    assert _config(db_path, "codex") == stripped
