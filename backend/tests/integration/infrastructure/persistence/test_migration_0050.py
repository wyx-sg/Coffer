"""Revision 0050: the distilled_sessions ledger is dropped.

Transcript distillation is removed, and with it the auto-distill catch-up sweep
that used this table to avoid distilling a settled session twice. The ledger
recorded work nothing performs any more.

The rows were machine-local bookkeeping — the vault export never carried this
table — so the drop loses no user content. What these tests pin is that the
drop survives the two states a real database can be in (table present from an
older install, table already absent) and that the chain still round-trips.

Reuses the alembic driving helpers from the round-trip suite so both tests
speak to the same real migration scripts and the same ``COFFER_DB_URL`` wiring.
"""

from __future__ import annotations

import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
    _alembic_version,
    _user_tables,
)

TABLE = "distilled_sessions"


def _seed_row(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"INSERT INTO {TABLE} "
        "(agent_name, session_id, content_sha256, distilled_at) "
        "VALUES (?, ?, ?, ?)",
        ("claude_code", "sess-1", "a" * 64, "2026-07-01T00:00:00+00:00"),
    )


def test_upgrade_drops_the_ledger(tmp_path, monkeypatch) -> None:
    """A database carrying the table — with rows — reaches head without it."""
    db_path = tmp_path / "c.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0049")
    assert TABLE in _user_tables(db_path)
    with sqlite3.connect(db_path) as conn:
        _seed_row(conn)
        conn.commit()

    command.upgrade(cfg, "0050")

    assert TABLE not in _user_tables(db_path)
    assert _alembic_version(db_path) == "0050"


def test_upgrade_is_idempotent_when_the_table_is_already_gone(tmp_path, monkeypatch) -> None:
    """An install that never had the table, or a partial earlier run, still
    upgrades rather than failing on a missing table."""
    db_path = tmp_path / "c.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0049")
    with sqlite3.connect(db_path) as conn:
        conn.execute(f"DROP TABLE {TABLE}")
        conn.commit()
    assert TABLE not in _user_tables(db_path)

    command.upgrade(cfg, "0050")

    assert TABLE not in _user_tables(db_path)
    assert _alembic_version(db_path) == "0050"


def test_downgrade_restores_the_shape_so_the_chain_round_trips(tmp_path, monkeypatch) -> None:
    """The contents are gone for good, but the schema must come back.

    0038's own downgrade drops this table on the way further down, so it has to
    exist again at 0049 or the chain breaks below it.
    """
    db_path = tmp_path / "c.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "head")
    assert TABLE not in _user_tables(db_path)

    command.downgrade(cfg, "0049")

    assert TABLE in _user_tables(db_path)
    # Recreated empty — the ledger's rows are not recoverable, and would mean
    # nothing without the code that wrote them.
    with sqlite3.connect(db_path) as conn:
        assert conn.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0] == 0
        # The unique constraint that made it a ledger must come back too, or a
        # downgraded database would accept duplicates the original rejected.
        indexes = conn.execute(f"PRAGMA index_list({TABLE})").fetchall()
    assert any(row[2] for row in indexes), "the uniqueness constraint must be restored"
