"""Revision 0108: agents collapse to one per type, named by it; agents, MCP
servers and skills lose their titles.

The kept agent is the connected one, then the enabled one, then the most
recently used; every reach list and channel default that named a dropped agent
is re-pointed at the kept one, and each dropped agent is logged.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid

import pytest
from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
    _alembic_version,
)


def _insert(conn, *, kind, name, config, enabled=1, updated="2026-09-01", scope=None, title=None):
    uid = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO resources (uid, kind, name, description, config_json, enabled,"
        " created_at, updated_at, scope_json, title, rev)"
        " VALUES (?, ?, ?, 'desc', ?, ?, '2026-09-01', ?, ?, ?, 1)",
        (uid, kind, name, json.dumps(config), enabled, updated, scope, title),
    )
    row_id = conn.execute("SELECT id FROM resources WHERE uid = ?", (uid,)).fetchone()[0]
    return uid, row_id


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    db_path = tmp_path / "agents.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    command.upgrade(_alembic_config(), "0107")
    return db_path


@pytest.mark.acceptance(
    spec="agent-registry", scenario="collapse duplicate agents to one per type on upgrade"
)
def test_0108_keeps_one_agent_per_type_and_repoints_references(db, tmp_path, caplog):
    work = tmp_path / "work-claude"
    with sqlite3.connect(db) as conn:
        # Two Claude Code agents: the disabled one was touched last, the
        # enabled one wins anyway. One Codex agent, renamed by the user.
        kept, kept_id = _insert(
            conn, kind="agent", name="claude-main", config={"type": "claude_code"}, title="Main"
        )
        dropped, dropped_id = _insert(
            conn,
            kind="agent",
            name="claude-work",
            config={"type": "claude_code", "config_dir": str(work)},
            enabled=0,
            updated="2026-09-20",
        )
        codex, _ = _insert(conn, kind="agent", name="my-codex", config={"type": "codex"})
        skill, skill_id = _insert(
            conn,
            kind="skill",
            name="a-skill",
            config={},
            title="A skill",
            scope=json.dumps({"agents": [dropped, kept, codex]}),
        )
        server, _ = _insert(
            conn,
            kind="mcp_server",
            name="fs",
            config={},
            title="Files",
            scope=json.dumps({"agents": [dropped]}),
        )
        channel, _ = _insert(
            conn,
            kind="channel",
            name="tg",
            config={"default_agent": dropped},
            title="Telegram",
        )
        conn.execute(
            "INSERT INTO skill_agent_bindings (skill_resource_id, agent_resource_id, enabled)"
            " VALUES (?, ?, 1)",
            (skill_id, dropped_id),
        )

    with caplog.at_level(logging.WARNING):
        command.upgrade(_alembic_config(), "0108")

    assert _alembic_version(db) == "0108"
    with sqlite3.connect(db) as conn:
        agents = conn.execute(
            "SELECT uid, name, title, description FROM resources WHERE kind = 'agent' ORDER BY name"
        ).fetchall()
        assert agents == [(kept, "claude-code", None, None), (codex, "codex", None, None)]
        scopes = dict(
            conn.execute("SELECT uid, scope_json FROM resources WHERE scope_json IS NOT NULL")
        )
        assert json.loads(scopes[skill]) == {"agents": [kept, codex]}
        assert json.loads(scopes[server]) == {"agents": [kept]}
        config, channel_title = conn.execute(
            "SELECT config_json, title FROM resources WHERE uid = ?", (channel,)
        ).fetchone()
        assert json.loads(config)["default_agent"] == kept
        # The channel keeps its title: only three kinds lose theirs.
        assert channel_title == "Telegram"
        titles = conn.execute(
            "SELECT title FROM resources WHERE kind IN ('skill', 'mcp_server')"
        ).fetchall()
        assert titles == [(None,), (None,)]
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM skill_agent_bindings WHERE agent_resource_id = ?",
                (dropped_id,),
            ).fetchone()[0]
            == 0
        )
    assert kept_id  # the kept row keeps its surrogate key and uid
    dropped_logs = [r.getMessage() for r in caplog.records if "agent_dropped" in r.getMessage()]
    assert len(dropped_logs) == 1
    assert dropped in dropped_logs[0] and "claude-work" in dropped_logs[0]
    assert f"kept={kept}" in dropped_logs[0]


def test_0108_keeps_the_connected_agent_over_a_more_recent_one(db, tmp_path):
    """The agent whose own Coffer MCP entry names its uid wins the tie-break."""
    connected_dir = tmp_path / "connected"
    connected_dir.mkdir()
    with sqlite3.connect(db) as conn:
        recent, _ = _insert(
            conn, kind="agent", name="recent", config={"type": "codex"}, updated="2026-09-29"
        )
        connected, _ = _insert(
            conn,
            kind="agent",
            name="connected",
            config={"type": "codex", "config_dir": str(connected_dir)},
        )
    (connected_dir / "config.toml").write_text(
        f'[mcp_servers.coffer]\ncommand = "/x/coffer-mcp-shim"\n'
        f'args = ["--agent-uid", "{connected}"]\n'
    )

    command.upgrade(_alembic_config(), "0108")

    with sqlite3.connect(db) as conn:
        rows = conn.execute("SELECT uid, name FROM resources WHERE kind = 'agent'").fetchall()
    assert rows == [(connected, "codex")]
    assert recent not in {uid for uid, _ in rows}


def test_0108_downgrade_leaves_the_collapsed_rows(db):
    with sqlite3.connect(db) as conn:
        uid, _ = _insert(conn, kind="agent", name="cc", config={"type": "claude_code"})
    cfg = _alembic_config()
    command.upgrade(cfg, "0108")
    command.downgrade(cfg, "0107")
    assert _alembic_version(db) == "0107"
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT name FROM resources WHERE uid = ?", (uid,)).fetchone() == (
            "claude-code",
        )
