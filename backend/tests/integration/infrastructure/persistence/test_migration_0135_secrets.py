"""Revision 0135: the secret store's stored names say "secret".

Seeded at 0134 with every old-shaped row the revision rewrites — a
``credentials`` row, a sync remote with ``credential_ref`` and
``include_credentials``, audit rows of the five ``credential_*`` event types,
an ``mcp_server`` citing its secrets under ``transport.credential_refs`` and a
``provider`` citing its key under ``credential_ref`` — plus rows it must leave
alone. Assertions read the database itself: the question is what is stored.
"""

from __future__ import annotations

import json
import sqlite3
import uuid

import pytest
from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
    _alembic_version,
    _user_tables,
)

_NOW = "2026-09-30T00:00:00+00:00"
_OLD_EVENTS = (
    "credential_set",
    "credential_read",
    "credential_deleted",
    "credential_migrated",
    "credential_revealed",
)


def _insert_resource(conn: sqlite3.Connection, kind: str, name: str, config: object) -> str:
    uid = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO resources (uid, kind, name, description, config_json, enabled,"
        " created_at, updated_at) VALUES (?, ?, ?, NULL, ?, 1, ?, ?)",
        (uid, kind, name, config if isinstance(config, str) else json.dumps(config), _NOW, _NOW),
    )
    return uid


def _configs(db_path) -> dict[str, object]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT name, config_json FROM resources").fetchall()
    out: dict[str, object] = {}
    for name, raw in rows:
        try:
            out[name] = json.loads(raw)
        except ValueError:
            out[name] = raw
    return out


def _columns(db_path, table: str) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _events(db_path) -> list[str]:
    with sqlite3.connect(db_path) as conn:
        return [r[0] for r in conn.execute("SELECT event_type FROM audit_log ORDER BY id")]


def _seed_at_0134(tmp_path, monkeypatch):
    db_path = tmp_path / "coffer.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, "0134")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO credentials (ref, ciphertext, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("mcp_server/abc/TOKEN", b"cipher", _NOW, _NOW),
        )
        conn.execute(
            "INSERT INTO sync_remotes (id, url, branch, credential_ref, include_credentials,"
            " interval_seconds, enabled, worktree_path, updated_at)"
            " VALUES (1, 'https://example.invalid/v.git', 'main', 'sync-push', 1, 3600, 1,"
            " '~/.coffer/sync', ?)",
            (_NOW,),
        )
        for event_type in (*_OLD_EVENTS, "resource_created"):
            conn.execute(
                "INSERT INTO audit_log (timestamp, event_type, actor, details_json)"
                " VALUES (?, ?, 'user', ?)",
                (_NOW, event_type, json.dumps({"ref": "mcp_server/abc/TOKEN"})),
            )
        _insert_resource(
            conn,
            "mcp_server",
            "files",
            {
                "transport": {
                    "type": "stdio",
                    "command": "files-mcp",
                    "env": {"CREDENTIAL_PATH": "/tmp/x"},
                    "credential_refs": {"TOKEN": "mcp_server/abc/TOKEN"},
                }
            },
        )
        _insert_resource(
            conn,
            "provider",
            "acme",
            {"protocol": "openai", "base_url": "https://acme/v1", "credential_ref": "p/acme/key"},
        )
        _insert_resource(conn, "skill", "notes", {"credential_ref": "not-a-provider"})
        _insert_resource(conn, "mcp_server", "broken", "not json")
        conn.commit()
    return db_path, cfg


def test_0135_renames_every_stored_credential_name_to_secret(tmp_path, monkeypatch):
    db_path, cfg = _seed_at_0134(tmp_path, monkeypatch)

    command.upgrade(cfg, "0135")

    assert _alembic_version(db_path) == "0135"
    tables = _user_tables(db_path)
    assert "secrets" in tables and "credentials" not in tables
    assert "last_used_at" in _columns(db_path, "secrets")
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT ref, ciphertext FROM secrets").fetchall() == [
            ("mcp_server/abc/TOKEN", b"cipher")
        ]
        remote = conn.execute(
            "SELECT secret_ref, include_secrets FROM sync_remotes WHERE id = 1"
        ).fetchone()
    assert remote == ("sync-push", 1)
    # The single-row CHECK survives the column rename.
    with sqlite3.connect(db_path) as conn, pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO sync_remotes (id, url, branch, include_secrets, interval_seconds,"
            " enabled, worktree_path, updated_at) VALUES (2, 'u', 'main', 0, 3600, 1, 'w', ?)",
            (_NOW,),
        )
    assert not ({"credential_ref", "include_credentials"} & _columns(db_path, "sync_remotes"))

    assert _events(db_path) == [
        "secret_set",
        "secret_read",
        "secret_deleted",
        "secret_migrated",
        "secret_revealed",
        "resource_created",
    ]

    configs = _configs(db_path)
    transport = configs["files"]["transport"]  # type: ignore[index]
    assert transport["secret_refs"] == {"TOKEN": "mcp_server/abc/TOKEN"}
    assert "credential_refs" not in transport
    # A user's own env name is data, not a key this revision owns.
    assert transport["env"] == {"CREDENTIAL_PATH": "/tmp/x"}
    assert configs["acme"] == {
        "protocol": "openai",
        "base_url": "https://acme/v1",
        "secret_ref": "p/acme/key",
    }
    # Only the two kinds that cite a secret under a "credential" key change.
    assert configs["notes"] == {"credential_ref": "not-a-provider"}
    assert configs["broken"] == "not json"


def test_0135_downgrade_restores_the_old_names_and_upgrades_again(tmp_path, monkeypatch):
    db_path, cfg = _seed_at_0134(tmp_path, monkeypatch)
    before = _configs(db_path)

    command.upgrade(cfg, "0135")
    command.downgrade(cfg, "0134")

    assert _alembic_version(db_path) == "0134"
    tables = _user_tables(db_path)
    assert "credentials" in tables and "secrets" not in tables
    assert "last_used_at" not in _columns(db_path, "credentials")
    assert {"credential_ref", "include_credentials"} <= _columns(db_path, "sync_remotes")
    assert _events(db_path) == [*_OLD_EVENTS, "resource_created"]
    assert _configs(db_path) == before

    command.upgrade(cfg, "0135")
    assert "secrets" in _user_tables(db_path)
    assert _events(db_path)[0] == "secret_set"
