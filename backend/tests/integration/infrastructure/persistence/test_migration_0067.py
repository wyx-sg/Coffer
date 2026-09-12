"""Revision 0067: model curation comes back OFF every channel.

A channel curates no models: a new conversation opens on the bound agent's own
CLI default and ``/model`` offers that agent's whole catalogue, refusing
nothing. The ``default_model`` + ``models`` pair 0063 moved here from the agent
therefore has no reader left, and this is the whole of the cleanup — no
load-time shim tolerates either key.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts, like the 0048/0049/0050/0051/0056/0061/0063 tests do.
"""

from __future__ import annotations

import json
import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
    _alembic_version,
)


def _seed(conn: sqlite3.Connection, kind: str, name: str, config: dict[str, object]) -> None:
    conn.execute(
        "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
        "VALUES (?, ?, ?, 1, '2026-09-01', '2026-09-01')",
        (kind, name, json.dumps(config)),
    )


def _config(db_path, name: str, kind: str = "channel") -> dict[str, object]:
    with sqlite3.connect(db_path) as conn:
        (raw,) = conn.execute(
            "SELECT config_json FROM resources WHERE kind = ? AND name = ?", (kind, name)
        ).fetchone()
    return json.loads(raw)


def test_0067_strips_both_keys_and_leaves_everything_else(tmp_path, monkeypatch):
    """Every channel row loses both keys, curated or not, and keeps the rest of
    its config. A CONNECTION's own curated set (0059) is a different field on a
    different kind and stays exactly where it is."""
    db_path = tmp_path / "channel_models.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0066")
    with sqlite3.connect(db_path) as conn:
        _seed(
            conn,
            "channel",
            "tg",
            {
                "channel_type": "telegram",
                "bot_token_ref": "channel/tg/bot-token",
                "default_agent": "claude_code",
                "default_model": "claude-opus-5",
                "models": ["claude-opus-5", "claude-haiku-4-5"],
            },
        )
        _seed(
            conn,
            "channel",
            "st",
            {
                "channel_type": "seatalk",
                "app_id": "a",
                "app_secret_ref": "channel/st/secret",
                "signing_secret_ref": "channel/st/signing",
                "default_model": None,
                "models": [],
            },
        )
        _seed(conn, "provider", "acme", {"protocol": "openai", "models": ["gpt-5"]})

    command.upgrade(cfg, "0067")
    assert _alembic_version(db_path) == "0067"

    curated = _config(db_path, "tg")
    assert "default_model" not in curated
    assert "models" not in curated
    # The strip rewrites the whole document, so assert it kept the rest.
    assert curated["bot_token_ref"] == "channel/tg/bot-token"
    assert curated["default_agent"] == "claude_code"

    uncurated = _config(db_path, "st")
    assert "default_model" not in uncurated
    assert "models" not in uncurated
    assert uncurated["app_id"] == "a"

    # A connection's curated set is not this revision's business.
    assert _config(db_path, "acme", kind="provider")["models"] == ["gpt-5"]


def test_0067_downgrade_restores_the_uncurated_default(tmp_path, monkeypatch):
    """Down puts both keys back in their uncurated form — no model pinned and an
    empty (no restriction) range, which is what every reader below this revision
    treats as "the agent's default, offer everything". Which model was pinned
    and which ids were ticked are not recoverable, and nothing above reads them
    any more, so there was nothing to preserve."""
    db_path = tmp_path / "channel_models_down.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0066")
    with sqlite3.connect(db_path) as conn:
        _seed(
            conn,
            "channel",
            "tg",
            {
                "channel_type": "telegram",
                "bot_token_ref": "channel/tg/bot-token",
                "default_model": "claude-opus-5",
                "models": ["claude-opus-5"],
            },
        )

    command.upgrade(cfg, "0067")
    command.downgrade(cfg, "0066")

    assert _alembic_version(db_path) == "0066"
    restored = _config(db_path, "tg")
    assert restored["default_model"] is None
    assert restored["models"] == []


def test_0067_leaves_an_unparseable_row_alone(tmp_path, monkeypatch):
    """A config JSON the migration cannot read is not guessed at — it is left
    exactly as found, and the upgrade still completes for every other row."""
    db_path = tmp_path / "channel_models_bad.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0066")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
            "VALUES ('channel', 'broken', 'not json', 1, '2026-09-01', '2026-09-01')"
        )
        _seed(
            conn,
            "channel",
            "tg",
            {"channel_type": "telegram", "bot_token_ref": "a/b", "models": ["claude-opus-5"]},
        )

    command.upgrade(cfg, "0067")

    with sqlite3.connect(db_path) as conn:
        (raw,) = conn.execute("SELECT config_json FROM resources WHERE name = 'broken'").fetchone()
    assert raw == "not json"
    assert "models" not in _config(db_path, "tg")
