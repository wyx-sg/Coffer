"""Revision 0065: the global embedding config NAMES a connection.

``embedding_config`` used to restate an endpoint — its own ``provider``,
``base_url`` and ``credential_ref``, a second place to type what the Connections
page already holds. It now carries ``connection``: the NAME of a ``provider``
resource (spec knowledge FR-077). The connection the stored row MEANT is the one
pointing at the same place, so the mapping matches on ``base_url`` first
(normalised for a trailing slash and case) and falls back to a shared
``credential_ref``. When nothing matches, the row keeps its dimensions and chunk
defaults but comes out with NO connection and ``enabled = 0`` — a state the app
already handles, where retrieval degrades to keyword/grep.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts, like the 0048/0049/0050/0051/0056/0061/0063/0064
tests do.
"""

from __future__ import annotations

import json
import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
    _alembic_version,
)


def _seed_provider(conn: sqlite3.Connection, name: str, config: dict[str, object]) -> None:
    conn.execute(
        "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
        "VALUES ('provider', ?, ?, 1, '2026-09-01', '2026-09-01')",
        (name, json.dumps(config)),
    )


def _seed_config(
    conn: sqlite3.Connection,
    *,
    provider: str | None,
    base_url: str | None,
    credential_ref: str | None,
    enabled: int = 1,
    dimensions: int = 1536,
) -> None:
    conn.execute(
        "INSERT INTO embedding_config "
        "(id, enabled, provider, model, base_url, credential_ref, dimensions, "
        " default_chunk_size, default_chunk_overlap, updated_at) "
        "VALUES (1, ?, ?, 'text-embedding-3-large', ?, ?, ?, 900, 100, '2026-09-01')",
        (enabled, provider, base_url, credential_ref, dimensions),
    )


def _columns(db_path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {row[1] for row in conn.execute("PRAGMA table_info(embedding_config)").fetchall()}


def _row(db_path) -> dict[str, object]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return dict(conn.execute("SELECT * FROM embedding_config WHERE id = 1").fetchone())


def _at_0064(tmp_path, monkeypatch, filename: str):
    db_path = tmp_path / filename
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, "0064")
    return db_path, cfg


def test_0065_names_the_connection_pointing_at_the_same_base_url(tmp_path, monkeypatch):
    """The match is on where the calls go, normalised for a trailing slash and
    case, and the row stays enabled: nothing about it has actually changed."""
    db_path, cfg = _at_0064(tmp_path, monkeypatch, "embedding_match.db")
    with sqlite3.connect(db_path) as conn:
        _seed_provider(
            conn,
            "other",
            {"protocol": "anthropic", "base_url": "https://api.anthropic.com"},
        )
        _seed_provider(
            conn,
            "acme",
            {
                "protocol": "openai",
                "base_url": "https://API.Acme.test/v1/",
                "credential_ref": "provider/acme/key",
            },
        )
        _seed_config(
            conn,
            provider="openai",
            base_url="https://api.acme.test/v1",
            credential_ref="embedding/key",
        )

    command.upgrade(cfg, "0065")
    assert _alembic_version(db_path) == "0065"

    row = _row(db_path)
    assert row["connection"] == "acme"
    assert row["enabled"] == 1
    assert row["model"] == "text-embedding-3-large"
    assert row["dimensions"] == 1536


def test_0065_falls_back_to_a_shared_credential_ref(tmp_path, monkeypatch):
    """Two configs sharing one vault entry are the same endpoint in practice, so
    a base URL that was corrected on only one side still maps."""
    db_path, cfg = _at_0064(tmp_path, monkeypatch, "embedding_by_ref.db")
    with sqlite3.connect(db_path) as conn:
        _seed_provider(
            conn,
            "acme",
            {
                "protocol": "openai",
                "base_url": "https://gateway.acme.test/v2",
                "credential_ref": "provider/acme/key",
            },
        )
        _seed_config(
            conn,
            provider="openai",
            base_url="https://api.acme.test/v1",
            credential_ref="provider/acme/key",
        )

    command.upgrade(cfg, "0065")

    row = _row(db_path)
    assert row["connection"] == "acme"
    assert row["enabled"] == 1


def test_0065_disables_a_config_that_matches_no_connection(tmp_path, monkeypatch):
    """Inventing a connection would put a half-real endpoint on the Connections
    page, so the row is left unnamed and switched off — while the settings that
    are still meaningful (width, chunking) survive for whoever picks a
    connection next."""
    db_path, cfg = _at_0064(tmp_path, monkeypatch, "embedding_orphan.db")
    with sqlite3.connect(db_path) as conn:
        _seed_provider(
            conn,
            "elsewhere",
            {
                "protocol": "openai",
                "base_url": "https://somewhere.else.test/v1",
                "credential_ref": "provider/elsewhere/key",
            },
        )
        _seed_config(
            conn,
            provider="openai",
            base_url="https://api.acme.test/v1",
            credential_ref="embedding/key",
            dimensions=1024,
        )

    command.upgrade(cfg, "0065")

    row = _row(db_path)
    assert row["connection"] is None
    assert row["enabled"] == 0
    assert row["dimensions"] == 1024
    assert row["default_chunk_size"] == 900
    assert row["default_chunk_overlap"] == 100


def test_0065_drops_the_three_restated_columns(tmp_path, monkeypatch):
    """The data is corrected in this revision, so no load-time shim reads the
    old columns afterwards — they are gone."""
    db_path, cfg = _at_0064(tmp_path, monkeypatch, "embedding_columns.db")
    with sqlite3.connect(db_path) as conn:
        _seed_provider(
            conn,
            "acme",
            {
                "protocol": "openai",
                "base_url": "https://api.acme.test/v1",
                "credential_ref": "provider/acme/key",
            },
        )
        _seed_config(
            conn,
            provider="openai",
            base_url="https://api.acme.test/v1",
            credential_ref="provider/acme/key",
        )
    assert {"provider", "base_url", "credential_ref"} <= _columns(db_path)

    command.upgrade(cfg, "0065")

    columns = _columns(db_path)
    assert "connection" in columns
    assert columns.isdisjoint({"provider", "base_url", "credential_ref"})
    # Everything the config still means is untouched.
    assert {"enabled", "model", "dimensions", "default_chunk_size", "default_chunk_overlap"} <= (
        columns
    )


def test_0065_is_idempotent_on_a_database_that_already_has_connection(tmp_path, monkeypatch):
    """A re-run matches nothing and rewrites nothing — the mapping evidence is
    gone by then, so a second pass must not disable a working config."""
    db_path, cfg = _at_0064(tmp_path, monkeypatch, "embedding_rerun.db")
    with sqlite3.connect(db_path) as conn:
        _seed_provider(
            conn,
            "acme",
            {
                "protocol": "openai",
                "base_url": "https://api.acme.test/v1",
                "credential_ref": "provider/acme/key",
            },
        )
        _seed_config(
            conn,
            provider="openai",
            base_url="https://api.acme.test/v1",
            credential_ref="provider/acme/key",
        )

    command.upgrade(cfg, "0065")
    command.downgrade(cfg, "0064")
    command.upgrade(cfg, "0065")

    row = _row(db_path)
    assert "connection" in _columns(db_path)
    # Down threw the evidence away (the restated columns come back empty), so up
    # again can only reach the unnamed, disabled state — never a wrong guess.
    assert row["connection"] is None
    assert row["enabled"] == 0


def test_0065_upgrades_a_database_that_never_configured_embedding(tmp_path, monkeypatch):
    """No singleton row at all: the column is added, nothing is invented, and
    the upgrade completes."""
    db_path, cfg = _at_0064(tmp_path, monkeypatch, "embedding_unset.db")

    command.upgrade(cfg, "0065")

    assert _alembic_version(db_path) == "0065"
    assert "connection" in _columns(db_path)
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM embedding_config").fetchone()[0] == 0
