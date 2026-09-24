"""Revision 0103: every SeaTalk channel loses its webhook-era keys.

SeaTalk inbound is websocket-only, so ``delivery``, ``signing_secret_ref``,
``public_base_url`` and ``tunnel_token_ref`` configure nothing and come off
every stored SeaTalk channel. The credential values the two removed refs cited
stay in the credential store: a migration that deletes secrets cannot be undone
by its downgrade.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts.
"""

from __future__ import annotations

import json
import sqlite3
import uuid

import pytest
from alembic import command

from coffer.domain.channel.config import SeaTalkChannelConfig, parse_channel_config
from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
    _alembic_version,
)

_WEBHOOK_KEYS = ("delivery", "signing_secret_ref", "public_base_url", "tunnel_token_ref")


def _seed(conn: sqlite3.Connection, name: str, config: dict[str, object] | str) -> None:
    conn.execute(
        "INSERT INTO resources (uid, kind, name, config_json, enabled, created_at, updated_at) "
        "VALUES (?, 'channel', ?, ?, 1, '2026-09-01', '2026-09-01')",
        (
            uuid.uuid4().hex,
            name,
            config if isinstance(config, str) else json.dumps(config),
        ),
    )


def _credential(conn: sqlite3.Connection, ref: str) -> None:
    conn.execute(
        "INSERT INTO credentials (ref, ciphertext, created_at, updated_at) "
        "VALUES (?, ?, '2026-09-01', '2026-09-01')",
        (ref, b"cipher-" + ref.encode()),
    )


def _raw(db_path, name: str) -> str:
    with sqlite3.connect(db_path) as conn:
        (raw,) = conn.execute(
            "SELECT config_json FROM resources WHERE name = ?", (name,)
        ).fetchone()
    return raw


def _config(db_path, name: str) -> dict[str, object]:
    return json.loads(_raw(db_path, name))


def _credentials(db_path) -> dict[str, bytes]:
    with sqlite3.connect(db_path) as conn:
        return dict(conn.execute("SELECT ref, ciphertext FROM credentials").fetchall())


_WEBHOOK_SEATALK = {
    "channel_type": "seatalk",
    "app_id": "app-1",
    "app_secret_ref": "channel/aa/app-secret",
    "delivery": "webhook",
    "signing_secret_ref": "channel/aa/signing-secret",
    "public_base_url": "https://bot.example.com",
    "tunnel_token_ref": "channel/aa/tunnel-token",
    "default_agent": "agent-uid",
    "runs_on": "machine-1",
    "require_mention": False,
}
_TELEGRAM = {
    "channel_type": "telegram",
    "bot_token_ref": "channel/bb/bot-token",
    "default_agent": "agent-uid",
    # Not a telegram key, but proof the revision reads channel_type before it
    # touches anything: a telegram row is never rewritten.
    "delivery": "webhook",
}


def _upgraded(tmp_path, monkeypatch):
    db_path = tmp_path / "seatalk_webhook.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, "0102")
    with sqlite3.connect(db_path) as conn:
        _seed(conn, "st", _WEBHOOK_SEATALK)
        _seed(conn, "tg", _TELEGRAM)
        _seed(conn, "broken", "not json")
        for ref in (
            "channel/aa/app-secret",
            "channel/aa/signing-secret",
            "channel/aa/tunnel-token",
            "channel/bb/bot-token",
        ):
            _credential(conn, ref)
    before = _credentials(db_path)
    command.upgrade(cfg, "0103")
    return db_path, cfg, before


@pytest.mark.acceptance(
    spec="channels/seatalk",
    scenario="a webhook-era seatalk channel keeps only its app credentials",
)
def test_a_webhook_era_seatalk_channel_keeps_only_its_app_credentials(tmp_path, monkeypatch):
    db_path, _cfg, before = _upgraded(tmp_path, monkeypatch)

    assert _alembic_version(db_path) == "0103"
    config = _config(db_path, "st")
    for key in _WEBHOOK_KEYS:
        assert key not in config
    # Its app credentials and its common fields are exactly as they were.
    assert config == {k: v for k, v in _WEBHOOK_SEATALK.items() if k not in _WEBHOOK_KEYS}
    parsed = parse_channel_config(config)
    assert isinstance(parsed, SeaTalkChannelConfig)
    assert (parsed.app_id, parsed.app_secret_ref) == ("app-1", "channel/aa/app-secret")
    # The credential values the removed refs cited are still in the store.
    assert _credentials(db_path) == before
    assert "channel/aa/signing-secret" in before
    assert "channel/aa/tunnel-token" in before


def test_a_telegram_channel_and_an_unreadable_row_are_untouched(tmp_path, monkeypatch):
    db_path, _cfg, _before = _upgraded(tmp_path, monkeypatch)

    assert _config(db_path, "tg") == _TELEGRAM
    assert _raw(db_path, "broken") == "not json"


def test_the_upgrade_is_idempotent(tmp_path, monkeypatch):
    db_path, cfg, _before = _upgraded(tmp_path, monkeypatch)
    once = _config(db_path, "st")

    command.downgrade(cfg, "0102")
    command.upgrade(cfg, "0103")

    assert _config(db_path, "st") == once


def test_the_downgrade_writes_websocket_delivery(tmp_path, monkeypatch):
    """The model below 0103 defaults ``delivery`` to webhook and then demands a
    signing secret the upgrade removed; ``websocket`` is readable by that build
    and true of the channel."""
    db_path, cfg, _before = _upgraded(tmp_path, monkeypatch)

    command.downgrade(cfg, "0102")

    assert _alembic_version(db_path) == "0102"
    config = _config(db_path, "st")
    assert config["delivery"] == "websocket"
    for key in ("signing_secret_ref", "public_base_url", "tunnel_token_ref"):
        assert key not in config
    assert _config(db_path, "tg") == _TELEGRAM
