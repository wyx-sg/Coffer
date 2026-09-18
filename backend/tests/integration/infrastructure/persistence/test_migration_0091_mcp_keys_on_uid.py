"""Revision 0091: the two MCP tables that keyed rows by a server's name.

``mcp_server_health.resource_name`` (a PRIMARY KEY) and
``mcp_invocations.resource_name`` both pointed at a server by the label its
owner may change, so both broke on a rename. 0091 re-keys them on the uid, and
the interesting part is what it does with a row whose name resolves to no
server: health rows are dropped, invocation rows are kept behind a marker. Each
answer is asserted below, because each was a decision rather than a consequence.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts, like the 0048/…/0069 tests do.
"""

from __future__ import annotations

import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)

JIRA_UID = "aa11bb22cc33dd44ee55ff6677889900"
CONFLUENCE_UID = "0099887766ff55ee44dd33cc22bb11aa"


def _seed_server(conn: sqlite3.Connection, uid: str, name: str) -> None:
    conn.execute(
        "INSERT INTO resources (uid, kind, name, config_json, enabled, created_at, updated_at)"
        " VALUES (?, 'mcp_server', ?, '{}', 1, '2026-09-18 00:00:00', '2026-09-18 00:00:00')",
        (uid, name),
    )


def _seed_health(conn: sqlite3.Connection, name: str, status: str) -> None:
    conn.execute(
        "INSERT INTO mcp_server_health (resource_name, status, checked_at)"
        " VALUES (?, ?, '2026-09-18 00:00:00')",
        (name, status),
    )


def _seed_invocation(conn: sqlite3.Connection, name: str, key: str) -> None:
    conn.execute(
        "INSERT INTO mcp_invocations (timestamp, resource_name, capability_type,"
        " capability_key, duration_ms, status)"
        " VALUES ('2026-09-18 00:00:00', ?, 'tool', ?, 1, 'ok')",
        (name, key),
    )


def _health(db_path) -> dict[str, str]:
    with sqlite3.connect(db_path) as conn:
        return dict(conn.execute("SELECT resource_uid, status FROM mcp_server_health"))


def _invocations(db_path) -> dict[str, str]:
    with sqlite3.connect(db_path) as conn:
        return dict(conn.execute("SELECT capability_key, resource_uid FROM mcp_invocations"))


def _at_0090(tmp_path, monkeypatch):
    """A vault one revision below, with two servers and rows naming three."""
    db_path = tmp_path / "mcp_uid.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, "0090")
    with sqlite3.connect(db_path) as conn:
        _seed_server(conn, JIRA_UID, "jira")
        _seed_server(conn, CONFLUENCE_UID, "confluence")
        conn.commit()
    return db_path, cfg


def test_0091_rekeys_the_rows_whose_server_is_still_here(tmp_path, monkeypatch):
    db_path, cfg = _at_0090(tmp_path, monkeypatch)
    with sqlite3.connect(db_path) as conn:
        _seed_health(conn, "jira", "healthy")
        _seed_health(conn, "confluence", "failing")
        _seed_invocation(conn, "jira", "jira_get_issue")
        conn.commit()

    command.upgrade(cfg, "0091")

    assert _health(db_path) == {JIRA_UID: "healthy", CONFLUENCE_UID: "failing"}
    assert _invocations(db_path) == {"jira_get_issue": JIRA_UID}


def test_0091_drops_a_health_row_for_a_server_that_is_gone(tmp_path, monkeypatch):
    """The health row is a cache of the last "test connection" and its column is
    a primary key, so there is nowhere to put "no identity". One click rebuilds
    it, and nothing is widened by its absence."""
    db_path, cfg = _at_0090(tmp_path, monkeypatch)
    with sqlite3.connect(db_path) as conn:
        _seed_health(conn, "jira", "healthy")
        _seed_health(conn, "deleted-last-week", "failing")
        conn.commit()

    command.upgrade(cfg, "0091")

    assert _health(db_path) == {JIRA_UID: "healthy"}


def test_0091_keeps_an_invocation_whose_server_is_gone_behind_a_marker(tmp_path, monkeypatch):
    """The opposite answer, for the opposite kind of table: the invocation log is
    history and may not be edited away. The label it carried survives behind a
    marker that is visibly not a uid, so the row joins to no resource — which is
    the truth about it."""
    db_path, cfg = _at_0090(tmp_path, monkeypatch)
    with sqlite3.connect(db_path) as conn:
        _seed_invocation(conn, "deleted-last-week", "old_tool")
        conn.commit()

    command.upgrade(cfg, "0091")

    assert _invocations(db_path) == {"old_tool": "deleted:deleted-last-week"}


def test_0091_leaves_coffers_own_builtin_rows_alone(tmp_path, monkeypatch):
    """``coffer`` is the sentinel Coffer's own built-in tools log under, and it
    stays that even when a registered server happens to be CALLED ``coffer`` —
    attributing Coffer's built-in calls to one of the user's servers would be a
    fabrication."""
    db_path, cfg = _at_0090(tmp_path, monkeypatch)
    with sqlite3.connect(db_path) as conn:
        _seed_server(conn, "ffffffffffffffffffffffffffffffff", "coffer")
        _seed_invocation(conn, "coffer", "recall")
        conn.commit()

    command.upgrade(cfg, "0091")

    assert _invocations(db_path) == {"recall": "coffer"}


def test_0091_downgrade_puts_the_names_back(tmp_path, monkeypatch):
    """Round trip: a resolvable uid gives back the server's current name and the
    marker gives back the name it was hiding. Health loses the row it already
    lost on the way up — the same trade, in the same direction."""
    db_path, cfg = _at_0090(tmp_path, monkeypatch)
    with sqlite3.connect(db_path) as conn:
        _seed_health(conn, "jira", "healthy")
        _seed_invocation(conn, "jira", "jira_get_issue")
        _seed_invocation(conn, "deleted-last-week", "old_tool")
        conn.commit()

    command.upgrade(cfg, "0091")
    command.downgrade(cfg, "0090")

    with sqlite3.connect(db_path) as conn:
        names = dict(conn.execute("SELECT capability_key, resource_name FROM mcp_invocations"))
        health = dict(conn.execute("SELECT resource_name, status FROM mcp_server_health"))
    assert names == {"jira_get_issue": "jira", "old_tool": "deleted-last-week"}
    assert health == {"jira": "healthy"}


def test_0091_is_idempotent_against_a_second_upgrade(tmp_path, monkeypatch):
    """A re-run must not double-prefix an already-marked row or touch a uid it
    already wrote — the guards that make the two updates order-independent are
    the same ones that make them safe to repeat."""
    db_path, cfg = _at_0090(tmp_path, monkeypatch)
    with sqlite3.connect(db_path) as conn:
        _seed_invocation(conn, "jira", "jira_get_issue")
        _seed_invocation(conn, "deleted-last-week", "old_tool")
        conn.commit()

    command.upgrade(cfg, "0091")
    before = _invocations(db_path)
    command.downgrade(cfg, "0090")
    command.upgrade(cfg, "0091")

    assert _invocations(db_path) == before
