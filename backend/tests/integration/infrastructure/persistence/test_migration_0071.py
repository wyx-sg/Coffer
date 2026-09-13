"""Revision 0071: a connection's ``compatible_agents`` becomes its framework scope.

The trap this migration exists for is that the two axes disagree on what UNSET
means — ``compatible_agents = null`` was the WIRE default (nothing at all for
ollama), while framework ``scope = null`` is EVERY agent. A rename would
therefore have silently widened an internal-only connection into both coding
agents and broken per-agent key routing. So every row is materialised: the
effective set is computed and written out concretely.

What is asserted here is exactly that: after the upgrade, the effective agent
set of an anthropic row, an openai row, an ollama row and an explicitly narrowed
row is bit-for-bit what ``resolved_compatible_agents`` would have answered
before it — and that the downgrade puts the value back where it came from.

Reuses the alembic driving helpers from the round-trip suite so this speaks to
the real migration scripts, like the 0048/0049/0050/0051 tests do.
"""

from __future__ import annotations

import json
import sqlite3

from alembic import command

from tests.integration.infrastructure.persistence.test_migrations_roundtrip import (
    _alembic_config,
)

#: What ``resolved_compatible_agents()`` answered before this revision, inlined
#: (the test must not import a model that has since dropped the field).
_EFFECTIVE_BEFORE: dict[str, list[str]] = {
    "anthropic": ["claude_code", "codex"],
    "openai": ["claude_code", "codex"],
    "ollama": [],
    "unknown": ["claude_code", "codex"],
}


def _seed(conn: sqlite3.Connection, name: str, protocol: str, compatible: object = ...) -> None:
    config: dict[str, object] = {
        "protocol": protocol,
        "base_url": "https://gateway.example/v1",
        "is_active": True,
    }
    if protocol != "ollama":
        config["credential_ref"] = f"{name}-key"
    if compatible is not ...:
        config["compatible_agents"] = compatible
    conn.execute(
        "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
        "VALUES ('provider', ?, ?, 1, '2026-09-01', '2026-09-01')",
        (name, json.dumps(config)),
    )


def _row(db_path, name: str) -> tuple[dict, object]:
    with sqlite3.connect(db_path) as conn:
        raw, scope_raw = conn.execute(
            "SELECT config_json, scope_json FROM resources WHERE kind = 'provider' AND name = ?",
            (name,),
        ).fetchone()
    return json.loads(raw), (json.loads(scope_raw) if scope_raw else None)


def _at_0070(tmp_path, monkeypatch, db_name: str):
    db_path = tmp_path / db_name
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()
    command.upgrade(cfg, "0070")
    return db_path, cfg


def test_0071_materialises_the_wire_default_into_the_scope(tmp_path, monkeypatch):
    """The rows that never named an agent: each keeps the reach its wire gave it,
    written out concretely so the framework's "null means every agent" cannot
    reinterpret it."""
    db_path, cfg = _at_0070(tmp_path, monkeypatch, "materialise.db")
    with sqlite3.connect(db_path) as conn:
        _seed(conn, "official", "anthropic")  # no compatible_agents key at all
        _seed(conn, "gateway", "openai", None)  # explicit null
        _seed(conn, "local", "ollama")
        _seed(conn, "probed", "unknown")
        conn.commit()

    command.upgrade(cfg, "0071")

    for name, protocol in (
        ("official", "anthropic"),
        ("gateway", "openai"),
        ("local", "ollama"),
        ("probed", "unknown"),
    ):
        config, scope = _row(db_path, name)
        assert scope == _EFFECTIVE_BEFORE[protocol], name
        # The dead key is gone: ProviderConfig forbids extras, so a row still
        # carrying it would be unreadable (no load-time shim is left behind).
        assert "compatible_agents" not in config, name


def test_0071_keeps_an_explicit_narrowing_exactly(tmp_path, monkeypatch):
    """The agnes case — an openai endpoint routed to Claude Code only — must not
    widen back to the wire default."""
    db_path, cfg = _at_0070(tmp_path, monkeypatch, "explicit.db")
    with sqlite3.connect(db_path) as conn:
        _seed(conn, "agnes", "openai", ["claude_code"])
        _seed(conn, "dupes", "unknown", ["codex", "claude_code", "codex"])
        _seed(conn, "none-at-all", "openai", [])
        conn.commit()

    command.upgrade(cfg, "0071")

    assert _row(db_path, "agnes")[1] == ["claude_code"]
    # Deduped, order preserving — as resolved_compatible_agents did.
    assert _row(db_path, "dupes")[1] == ["codex", "claude_code"]
    # An empty list reached no agent before and is dormant now: same reach.
    assert _row(db_path, "none-at-all")[1] == []


def test_0071_downgrade_round_trips(tmp_path, monkeypatch):
    """Down and up again lands on the same effective set, so the chain is
    runnable in both directions without changing any connection's reach."""
    db_path, cfg = _at_0070(tmp_path, monkeypatch, "roundtrip.db")
    with sqlite3.connect(db_path) as conn:
        _seed(conn, "official", "anthropic")
        _seed(conn, "agnes", "openai", ["claude_code"])
        _seed(conn, "local", "ollama")
        conn.commit()

    command.upgrade(cfg, "0071")
    command.downgrade(cfg, "0070")

    # The field is back, carrying the effective set, and the scope is cleared.
    for name, expected in (
        ("official", ["claude_code", "codex"]),
        ("agnes", ["claude_code"]),
        ("local", []),
    ):
        config, scope = _row(db_path, name)
        assert config["compatible_agents"] == expected, name
        assert scope is None, name

    command.upgrade(cfg, "0071")

    assert _row(db_path, "official")[1] == ["claude_code", "codex"]
    assert _row(db_path, "agnes")[1] == ["claude_code"]
    assert _row(db_path, "local")[1] == []


def test_0071_leaves_a_shape_drifted_row_alone(tmp_path, monkeypatch):
    """A config that is not an object is not this script's to fix, and must not
    stop the pass for the rows that are fine. (The table's own CHECK keeps
    outright malformed JSON out, so this is the drift that can actually
    reach the script.)"""
    db_path, cfg = _at_0070(tmp_path, monkeypatch, "drifted.db")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at) "
            "VALUES ('provider', 'broken', '\"not an object\"', 1, '2026-09-01', '2026-09-01')"
        )
        _seed(conn, "official", "anthropic")
        conn.commit()

    command.upgrade(cfg, "0071")

    with sqlite3.connect(db_path) as conn:
        (raw,) = conn.execute("SELECT config_json FROM resources WHERE name = 'broken'").fetchone()
    assert raw == '"not an object"'
    assert _row(db_path, "official")[1] == ["claude_code", "codex"]


def test_0071_run_twice_changes_nothing(tmp_path, monkeypatch):
    """Re-running the upgrade over already-materialised rows must change nothing.

    The bug this pins: once the key is stripped, "no ``compatible_agents``"
    looks exactly like "never named one", so re-resolving falls back to the
    WIRE DEFAULT and overwrites the materialised value — silently widening the
    very connection this migration exists to leave alone, and re-waking one the
    user deliberately scoped to nothing. The stored scope is what tells the two
    apart, so the second pass has to consult it.

    The version table is wound back WITHOUT running ``downgrade`` (which would
    restore the key and hide the bug); that is what a hand-run, a stamp, or a
    replayed migration chain does to the data.
    """
    db_path, cfg = _at_0070(tmp_path, monkeypatch, "twice.db")
    with sqlite3.connect(db_path) as conn:
        _seed(conn, "agnes", "openai", ["claude_code"])
        _seed(conn, "dormant", "openai", [])
        _seed(conn, "wide", "anthropic")
        conn.commit()

    command.upgrade(cfg, "0071")
    names = ("agnes", "dormant", "wide")
    after_once = {name: _row(db_path, name) for name in names}
    assert after_once["agnes"][1] == ["claude_code"]
    assert after_once["dormant"][1] == []

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE alembic_version SET version_num = '0070'")
        conn.commit()
    command.upgrade(cfg, "0071")

    for name in names:
        assert _row(db_path, name) == after_once[name], name
