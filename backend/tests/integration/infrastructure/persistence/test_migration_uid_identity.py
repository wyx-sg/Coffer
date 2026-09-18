"""0089 and 0090 — the identity backfill and the cross-reference rewrite.

These two run once, over the user's real vault, and both can do damage that
nothing reports: 0089 has to produce the SAME uid on two machines that never
talk to each other, and 0090 rewrites allow-lists, where every mistake in the
widening direction is invisible — a resource simply becomes live somewhere the
user had said it should not be.

The scope rewrite is tested against all THREE vocabularies the column turned out
to hold, because that is what made it dangerous: `skill` and `channel` scopes
store agent resource NAMES, `provider` scopes store agent TYPES, and a rewrite
that knew about only the first silently emptied every connection's reach —
half-silently, because one type string happened to collide with one default
agent name and one did not.

Kept in its own module rather than appended to ``test_migrations_roundtrip.py``:
that file is the chain's round-trip proof and is already long, and these are
about the semantics of two revisions rather than the lineage.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import uuid

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig

MIGRATIONS = pathlib.Path("backend/coffer/infrastructure/persistence/migrations")
NAMESPACE = uuid.UUID("cd180388-8e6e-4bd0-a240-a8facba5ce53")


def _alembic_config() -> AlembicConfig:
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    return cfg


def _agent(name: str, agent_type: str) -> tuple[str, ...]:
    return (
        "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
        f"VALUES ('agent', '{name}', "
        f"'{json.dumps({'type': agent_type, 'config_dir': f'/tmp/{name}'})}', "
        "1, '2026-01-01', '2026-01-01')",
    )


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "uid.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{path}")
    return path


def test_0089_derives_the_same_uid_on_two_independent_machines(db, tmp_path, monkeypatch):
    """The whole point of deriving rather than randomising.

    Two vaults that have never met must compute one identity for one resource,
    because the next converge round matches documents by uid. If this drifts,
    two machines publish the same resource twice and three-way-merge two
    unrelated documents into one.
    """
    cfg = _alembic_config()
    command.upgrade(cfg, "0088")
    with sqlite3.connect(db) as conn:
        conn.execute(*_agent("claude-code", "claude_code"))
        conn.execute(
            "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
            "VALUES ('skill', 'writing', '{}', 1, '2026-01-01', '2026-01-01')"
        )
    command.upgrade(cfg, "0089")
    with sqlite3.connect(db) as conn:
        first = dict(conn.execute("SELECT name, uid FROM resources").fetchall())

    # A second machine, same two resources, its own database and its own row ids.
    other = tmp_path / "other.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{other}")
    cfg2 = _alembic_config()
    command.upgrade(cfg2, "0088")
    with sqlite3.connect(other) as conn:
        # Inserted in the OTHER order, so the row ids differ.
        conn.execute(
            "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
            "VALUES ('skill', 'writing', '{}', 1, '2026-01-01', '2026-01-01')"
        )
        conn.execute(*_agent("claude-code", "claude_code"))
    command.upgrade(cfg2, "0089")
    with sqlite3.connect(other) as conn:
        second = dict(conn.execute("SELECT name, uid FROM resources").fetchall())
        ids = dict(conn.execute("SELECT name, id FROM resources").fetchall())

    assert first == second
    assert first["writing"] == uuid.uuid5(NAMESPACE, "skill:writing").hex
    # And the row ids really did differ, so the uids agreeing is not a
    # coincidence of both machines numbering their rows the same way.
    with sqlite3.connect(db) as conn:
        assert dict(conn.execute("SELECT name, id FROM resources").fetchall()) != ids


def test_0089_is_idempotent(db):
    cfg = _alembic_config()
    command.upgrade(cfg, "0088")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
            "VALUES ('skill', 'writing', '{}', 1, '2026-01-01', '2026-01-01')"
        )
    command.upgrade(cfg, "0089")
    with sqlite3.connect(db) as conn:
        before = conn.execute("SELECT uid FROM resources").fetchone()[0]
    command.downgrade(cfg, "0088")
    command.upgrade(cfg, "0089")
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT uid FROM resources").fetchone()[0] == before


def test_0090_rewrites_all_three_scope_vocabularies(db):
    """Names, types, and a type with TWO agents behind it."""
    cfg = _alembic_config()
    command.upgrade(cfg, "0088")
    with sqlite3.connect(db) as conn:
        conn.execute(*_agent("claude-code", "claude_code"))
        conn.execute(*_agent("claude-work", "claude_code"))  # a second install
        conn.execute(*_agent("codex", "codex"))
        # A skill scope: agent resource NAMES.
        conn.execute(
            "INSERT INTO resources "
            "(kind, name, config_json, scope_json, enabled, created_at, updated_at) "
            "VALUES ('skill', 'writing', '{}', ?, 1, '2026-01-01', '2026-01-01')",
            (json.dumps({"agents": ["claude-code"]}),),
        )
        # A provider scope: agent TYPES. `claude_code` has two agents behind it.
        conn.execute(
            "INSERT INTO resources "
            "(kind, name, config_json, scope_json, enabled, created_at, updated_at) "
            "VALUES ('provider', 'anthropic', '{}', ?, 1, '2026-01-01', '2026-01-01')",
            (json.dumps({"agents": ["claude_code"]}),),
        )
    command.upgrade(cfg, "0090")

    with sqlite3.connect(db) as conn:
        uids = dict(conn.execute("SELECT name, uid FROM resources").fetchall())
        scopes = {
            name: json.loads(scope)
            for name, scope in conn.execute(
                "SELECT name, scope_json FROM resources WHERE scope_json IS NOT NULL"
            ).fetchall()
        }

    assert scopes["writing"] == {"agents": [uids["claude-code"]]}
    # Expanded to EVERY agent of that type. Taking only the first would have
    # silently stopped projecting this connection into the second install.
    assert sorted(scopes["anthropic"]["agents"]) == sorted(
        [uids["claude-code"], uids["claude-work"]]
    )


def test_0090_never_turns_a_restriction_into_no_restriction(db):
    """An all-unresolvable allow-list becomes ``[]``, never ``NULL``.

    ``NULL`` means unscoped — active for EVERY agent. A row the user had
    narrowed must never come out of a migration wider than it went in, and this
    is the one input where a careless implementation does exactly that.
    """
    cfg = _alembic_config()
    command.upgrade(cfg, "0088")
    with sqlite3.connect(db) as conn:
        conn.execute(*_agent("codex", "codex"))
        conn.execute(
            "INSERT INTO resources "
            "(kind, name, config_json, scope_json, enabled, created_at, updated_at) "
            "VALUES ('skill', 'orphaned', '{}', ?, 1, '2026-01-01', '2026-01-01')",
            (json.dumps({"agents": ["an-agent-that-was-deleted"]}),),
        )
        # An unrestricted scope has nothing to narrow and must stay that way.
        conn.execute(
            "INSERT INTO resources "
            "(kind, name, config_json, scope_json, enabled, created_at, updated_at) "
            "VALUES ('skill', 'open', '{}', ?, 1, '2026-01-01', '2026-01-01')",
            (json.dumps({"agents": None}),),
        )
    command.upgrade(cfg, "0090")

    with sqlite3.connect(db) as conn:
        rows = dict(
            conn.execute("SELECT name, scope_json FROM resources WHERE kind = 'skill'").fetchall()
        )
    assert json.loads(rows["orphaned"]) == {"agents": []}
    assert json.loads(rows["open"]) == {"agents": None}


def test_0090_leaves_an_unresolvable_default_agent_verbatim(db):
    """A binding that cannot be resolved must fail where the user can see it.

    Clearing it would be a channel that silently stops answering, with nothing
    on screen saying why. Left as it was, the kind's own validation refuses it
    the next time the channel is touched, with the original value still there.
    """
    cfg = _alembic_config()
    command.upgrade(cfg, "0088")
    with sqlite3.connect(db) as conn:
        conn.execute(*_agent("codex", "codex"))
        conn.execute(
            "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
            "VALUES ('channel', 'bound', ?, 1, '2026-01-01', '2026-01-01')",
            (json.dumps({"default_agent": "codex"}),),
        )
        conn.execute(
            "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
            "VALUES ('channel', 'broken', ?, 1, '2026-01-01', '2026-01-01')",
            (json.dumps({"default_agent": "an_agent_type_nobody_has"}),),
        )
    command.upgrade(cfg, "0090")

    with sqlite3.connect(db) as conn:
        uids = dict(conn.execute("SELECT name, uid FROM resources").fetchall())
        configs = {
            name: json.loads(cfg_json)
            for name, cfg_json in conn.execute(
                "SELECT name, config_json FROM resources WHERE kind = 'channel'"
            ).fetchall()
        }
    assert configs["bound"]["default_agent"] == uids["codex"]
    assert configs["broken"]["default_agent"] == "an_agent_type_nobody_has"
