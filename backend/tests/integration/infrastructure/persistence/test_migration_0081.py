"""0081 rewrites a channel's scope into agent resource names (spec channels FR-079).

The reader changed underneath the data. Until 0081's revision a channel's scope
was compared straight against its ``default_agent``, so the only value it could
hold was the agent KEY; now the comparison is translated through the registry,
and a stored key names a resource the vault does not hold — a channel that
would drive nothing, dark on upgrade without a word. Same failure mode as 0080,
different field.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migration_0079 import _seed
from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)


def _at_0080(tmp_path, monkeypatch, db_name: str):
    """A throwaway vault at the revision just below 0081."""
    db_path = tmp_path / db_name
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    (tmp_path / "daemon-config.json").write_text(
        json.dumps({"version": 1, "port": 8000, "machine_id": "b7a5160dc1ef128f"})
    )
    cfg = _alembic_config()
    command.upgrade(cfg, "0080")
    return db_path, cfg


def _scope(db_path: pathlib.Path, name: str) -> dict | None:
    with sqlite3.connect(db_path) as conn:
        [(raw,)] = conn.execute(
            "SELECT scope_json FROM resources WHERE kind = 'channel' AND name = ?", (name,)
        ).fetchall()
    return None if raw is None else json.loads(raw)


def _set_scope(db_path: pathlib.Path, name: str, scope: dict) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE resources SET scope_json = ? WHERE kind = 'channel' AND name = ?",
            (json.dumps(scope), name),
        )
        conn.commit()


def _vault(tmp_path, monkeypatch, db_name: str, scope: dict, *, agents=(("cc", "claude_code"),)):
    db_path, cfg = _at_0080(tmp_path, monkeypatch, db_name)
    for name, agent_key in agents:
        _seed(db_path, "agent", name, {"type": agent_key})
    _seed(db_path, "channel", "tg", {"channel_type": "telegram", "default_agent": "claude_code"})
    _set_scope(db_path, "tg", scope)
    return db_path, cfg


def test_0081_replaces_a_stored_agent_key_with_the_resource_that_has_it(tmp_path, monkeypatch):
    """The whole point: the channel keeps driving the agent it was driving."""
    db_path, cfg = _vault(tmp_path, monkeypatch, "key.db", {"agents": ["claude_code"]})

    command.upgrade(cfg, "0081")

    assert _scope(db_path, "tg") == {"agents": ["cc"]}


def test_0081_reaches_every_resource_of_that_type(tmp_path, monkeypatch):
    """Two Claude Code agents against different config dirs are two resources
    and one key; naming the key meant both, so both survive the translation."""
    db_path, cfg = _vault(
        tmp_path,
        monkeypatch,
        "two.db",
        {"agents": ["claude_code"]},
        agents=(("cc-work", "claude_code"), ("cc-home", "claude_code")),
    )

    command.upgrade(cfg, "0081")

    assert _scope(db_path, "tg") == {"agents": ["cc-home", "cc-work"]}


def test_0081_leaves_a_scope_already_naming_resources_alone(tmp_path, monkeypatch):
    db_path, cfg = _vault(tmp_path, monkeypatch, "names.db", {"agents": ["cc"]})

    command.upgrade(cfg, "0081")

    assert _scope(db_path, "tg") == {"agents": ["cc"]}


def test_0081_keeps_a_dormant_channel_dormant(tmp_path, monkeypatch):
    """``[]`` is the owner's off switch, not a vocabulary to translate."""
    db_path, cfg = _vault(tmp_path, monkeypatch, "dormant.db", {"agents": []})

    command.upgrade(cfg, "0081")

    assert _scope(db_path, "tg") == {"agents": []}


def test_0081_leaves_a_name_it_cannot_place_exactly_as_found(tmp_path, monkeypatch):
    """Neither a resource nor a key this vault knows. There is nothing to
    translate it into, and guessing would widen a reach the owner narrowed."""
    db_path, cfg = _vault(tmp_path, monkeypatch, "unknown.db", {"agents": ["retired-agent"]})

    command.upgrade(cfg, "0081")

    assert _scope(db_path, "tg") == {"agents": ["retired-agent"]}


def test_0081_touches_no_other_kind(tmp_path, monkeypatch):
    """Every other kind's scope already names agent resources — it is only the
    channel that was forced into the other vocabulary."""
    db_path, cfg = _at_0080(tmp_path, monkeypatch, "kinds.db")
    _seed(db_path, "agent", "cc", {"type": "claude_code"})
    _seed(db_path, "memory", "notes", {})
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE resources SET scope_json = ? WHERE name = 'notes'",
            (json.dumps({"agents": ["claude_code"]}),),
        )
        conn.commit()

    command.upgrade(cfg, "0081")

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT scope_json FROM resources WHERE name = 'notes'").fetchall()
    assert json.loads(rows[0][0]) == {"agents": ["claude_code"]}
