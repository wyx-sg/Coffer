"""0105 enables every ``knowledge`` and ``memory`` row stored disabled.

The two kinds lose their enabled switch (spec resource-framework "Address every
resource by an immutable uid through one kind-agnostic surface"), so a row left
disabled would be a state nothing can show or change. The interesting assertion
is the negative one: a disabled row of any other kind — where disabled is a
real answer its owner chose — stays disabled.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)


def _at_0104(tmp_path, monkeypatch, db_name: str):  # type: ignore[no-untyped-def]
    """A throwaway vault at the revision just below 0105."""
    db_path = tmp_path / db_name
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    (tmp_path / "daemon-config.json").write_text(
        json.dumps({"version": 1, "port": 38470, "machine_id": "b7a5160dc1ef128f"})
    )
    cfg = _alembic_config()
    command.upgrade(cfg, "0104")
    return db_path, cfg


def _seed(db_path: pathlib.Path, kind: str, name: str, *, enabled: bool) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO resources (uid, kind, name, config_json, enabled, created_at,"
            " updated_at) VALUES (?, ?, ?, '{}', ?, '2026-09-28 00:00:00',"
            " '2026-09-28 00:00:00')",
            (f"uid-{kind}-{name}", kind, name, int(enabled)),
        )
        conn.commit()


def _enabled(db_path: pathlib.Path) -> dict[tuple[str, str], bool]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT kind, name, enabled FROM resources").fetchall()
    return {(kind, name): bool(flag) for kind, name, flag in rows}


def test_0105_enables_knowledge_and_memory_and_nothing_else(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    db_path, cfg = _at_0104(tmp_path, monkeypatch, "mixed.db")
    _seed(db_path, "knowledge", "shopee", enabled=False)
    _seed(db_path, "knowledge", "personal", enabled=True)
    _seed(db_path, "memory", "coffer", enabled=False)
    _seed(db_path, "skill", "reviewer", enabled=False)
    _seed(db_path, "mcp_server", "fs", enabled=False)

    command.upgrade(cfg, "0105")

    assert _enabled(db_path) == {
        ("knowledge", "shopee"): True,
        ("knowledge", "personal"): True,
        ("memory", "coffer"): True,
        # Disabled is a real answer for a kind that keeps its switch.
        ("skill", "reviewer"): False,
        ("mcp_server", "fs"): False,
    }


def test_0105_is_idempotent_and_its_downgrade_writes_nothing(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    db_path, cfg = _at_0104(tmp_path, monkeypatch, "idem.db")
    _seed(db_path, "memory", "coffer", enabled=False)

    command.upgrade(cfg, "0105")
    after_first = _enabled(db_path)
    command.downgrade(cfg, "0104")
    assert _enabled(db_path) == after_first
    command.upgrade(cfg, "0105")

    assert after_first == {("memory", "coffer"): True}
    assert _enabled(db_path) == after_first
