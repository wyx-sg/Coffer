"""Revision 0069: the audit rows for a retired event go with the event.

``daemon_port_set`` left ``AuditEventType`` along with the HTTP route that was
its only writer — the port is a CLI-only setting now, and the CLI cannot take
the event over because it has to work with no daemon running (spec daemon FR-011). 0055 set the rule
for what happens to the rows such an event already
wrote: they go, because a row whose ``event_type`` nothing in the code can name
is a row every reader has to cope with and none can label.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts, like the 0048/0049/0050/0051/0056/0061/0063/0068
tests do.
"""

from __future__ import annotations

import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)


def _seed_audit(conn: sqlite3.Connection, event_type: str, resource_name: str) -> None:
    conn.execute(
        "INSERT INTO audit_log (timestamp, event_type, resource_kind, resource_name, "
        "actor, details_json) VALUES ('2026-09-12 00:00:00', ?, 'setting', ?, 'ui', '{}')",
        (event_type, resource_name),
    )


def _event_types(db_path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        return [row[0] for row in conn.execute("SELECT event_type FROM audit_log ORDER BY id")]


def test_0069_deletes_the_retired_event_and_nothing_else(tmp_path, monkeypatch):
    """Only ``daemon_port_set`` rows go. A live event that happens to sit either
    side of them in the table is untouched — the filter is on the value, not on
    a range or a date."""
    db_path = tmp_path / "audit_purge.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0068")
    with sqlite3.connect(db_path) as conn:
        _seed_audit(conn, "resource_created", "keeper-before")
        _seed_audit(conn, "daemon_port_set", "daemon")
        _seed_audit(conn, "daemon_port_set", "daemon")
        _seed_audit(conn, "token_rotated", "keeper-after")
        conn.commit()

    command.upgrade(cfg, "0069")

    assert _event_types(db_path) == ["resource_created", "token_rotated"]


def test_0069_is_a_no_op_on_a_vault_that_never_wrote_the_event(tmp_path, monkeypatch):
    """The Settings panel that fired this event existed for a day, so most
    vaults have no such row. Matching none must be ordinary, not an error."""
    db_path = tmp_path / "audit_purge_clean.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0068")
    with sqlite3.connect(db_path) as conn:
        _seed_audit(conn, "resource_created", "untouched")
        conn.commit()

    command.upgrade(cfg, "0069")

    assert _event_types(db_path) == ["resource_created"]


def test_0069_downgrade_leaves_the_schema_usable(tmp_path, monkeypatch):
    """The purge cannot be undone — the rows recorded an event the product no
    longer has — but the downgrade must still run and leave the table working,
    so a vault stepping back through this revision is not stranded."""
    db_path = tmp_path / "audit_purge_down.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0069")
    command.downgrade(cfg, "0068")

    with sqlite3.connect(db_path) as conn:
        _seed_audit(conn, "resource_created", "still-writable")
        conn.commit()
    assert _event_types(db_path) == ["resource_created"]
