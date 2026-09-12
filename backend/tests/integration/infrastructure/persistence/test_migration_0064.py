"""Revision 0064: every curated model entry gains a ``modality``.

A connection's curated set used to be bare ids, which assumed everything an
endpoint serves is a chat model. It is not (spec provider-switching FR-029), so
each entry becomes ``{"id": ..., "modality": ...}``. Rows written earlier have
no answer, and the only evidence is the id — so this revision guesses ONCE from
the name. Afterwards the stored modality is the truth: nothing re-infers at load
time, and the user corrects a wrong guess from the connection's model table.

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


def _config(db_path, name: str, kind: str = "provider") -> dict[str, object]:
    with sqlite3.connect(db_path) as conn:
        (raw,) = conn.execute(
            "SELECT config_json FROM resources WHERE kind = ? AND name = ?", (kind, name)
        ).fetchone()
    return json.loads(raw)


def test_0064_infers_a_modality_for_every_plain_id(tmp_path, monkeypatch):
    """The guess, once, by name — and everything that is not obviously another
    kind stays ``text``, which is what these sets were curated as."""
    db_path = tmp_path / "modality.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0063")
    with sqlite3.connect(db_path) as conn:
        _seed(
            conn,
            "provider",
            "acme",
            {
                "protocol": "openai",
                "base_url": "https://api.acme.test/v1",
                "models": [
                    "gpt-5",
                    "text-embedding-3-large",
                    "dall-e-3",
                    "sora-2",
                    "whisper-1",
                    "claude-opus-4-6",
                ],
            },
        )
        _seed(conn, "provider", "bare", {"protocol": "ollama", "models": []})

    command.upgrade(cfg, "0064")
    assert _alembic_version(db_path) == "0064"

    acme = _config(db_path, "acme")
    assert acme["models"] == [
        {"id": "gpt-5", "modality": "text"},
        {"id": "text-embedding-3-large", "modality": "embedding"},
        {"id": "dall-e-3", "modality": "image"},
        {"id": "sora-2", "modality": "video"},
        {"id": "whisper-1", "modality": "audio"},
        {"id": "claude-opus-4-6", "modality": "text"},
    ]
    # The rewrite touches the whole document, so assert it kept the rest.
    assert acme["base_url"] == "https://api.acme.test/v1"
    # An empty (unrestricted) set has nothing to guess at and stays empty.
    assert _config(db_path, "bare")["models"] == []


def test_0064_leaves_an_already_converted_entry_alone(tmp_path, monkeypatch):
    """Idempotent, and the user's answer beats the guess: an entry already
    stored as an object is passed through untouched even when its id would have
    been read as another kind."""
    db_path = tmp_path / "modality_idempotent.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0063")
    with sqlite3.connect(db_path) as conn:
        _seed(
            conn,
            "provider",
            "mixed",
            {
                "protocol": "openai",
                "models": [
                    # An id that LOOKS like an embedding model, classified by hand.
                    {"id": "text-embedding-3-large", "modality": "text"},
                    "gpt-5",
                ],
            },
        )

    command.upgrade(cfg, "0064")
    first = _config(db_path, "mixed")["models"]
    assert first == [
        {"id": "text-embedding-3-large", "modality": "text"},
        {"id": "gpt-5", "modality": "text"},
    ]

    # Re-running the revision (down then up) changes nothing about the shape;
    # only the hand-set modality is lost, because down deliberately drops it.
    command.downgrade(cfg, "0063")
    assert _config(db_path, "mixed")["models"] == ["text-embedding-3-large", "gpt-5"]
    command.upgrade(cfg, "0064")
    assert _config(db_path, "mixed")["models"] == [
        {"id": "text-embedding-3-large", "modality": "embedding"},
        {"id": "gpt-5", "modality": "text"},
    ]


def test_0064_leaves_other_kinds_alone(tmp_path, monkeypatch):
    """A channel's allowed model range is a different field on a different kind
    — this revision reshapes connections and nothing else. (A config that is not
    valid JSON cannot be seeded at all: the table's own CHECK rejects it.)"""
    db_path = tmp_path / "modality_other_kinds.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0063")
    with sqlite3.connect(db_path) as conn:
        _seed(conn, "channel", "seatalk", {"models": ["gpt-5"]})
        _seed(conn, "provider", "acme", {"protocol": "openai", "models": ["gpt-5"]})

    command.upgrade(cfg, "0064")
    assert _alembic_version(db_path) == "0064"

    assert _config(db_path, "seatalk", kind="channel")["models"] == ["gpt-5"]
    assert _config(db_path, "acme")["models"] == [{"id": "gpt-5", "modality": "text"}]
