"""Genuine Alembic migration round-trip test.

Drives the real migration scripts against a throwaway SQLite file and asserts
the schema is created on ``upgrade head`` and fully torn down on
``downgrade base`` — i.e. proves the ``downgrade()`` functions actually run and
that the migration chain is reversible and idempotent.

``env.py`` reads ``COFFER_DB_URL`` (an async ``sqlite+aiosqlite://`` URL) and
runs migrations through the async engine, so the test sets that env var via
monkeypatch and lets ``env.py`` do the async/sync conversion itself.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3

from alembic import command
from alembic.config import Config as AlembicConfig

HEAD_REVISION = "0020"

# Tables that should exist once the full migration chain has been applied.
# The agent kind (spec 004-agent-registry) needs no table of its own — agents
# live in the generic `resources` table. The skill kind (spec 005-skill-manager)
# adds skill_agent_bindings in revision 0005. The knowledge_base kind (spec
# 006-knowledge-base) replaces the old per-kind ``kb_documents`` table with the
# unified ``documents`` + ``chunks`` + ``documents_fts`` (FTS5) schema in 0006;
# the memory kind (spec 007-memory) reuses that same unified schema (0007 adds
# no table of its own), 0008 adds ``memory_projection_bindings`` for the
# agent-side memory projection (which agents a store is projected into), and
# 0009 adds ``memory_store_project_roots`` mapping a project store to the
# absolute git-root it was provisioned from. 0015 adds ``channel_peers``
# (spec 009-channels: the paired owner of a messaging channel); 0016 adds the
# ``credentials`` table for the Fernet-encrypted secret store (envelope
# encryption); 0017 adds no table — it rekeys ``chunks.id`` /
# ``documents_fts.chunk_id`` to the per-store namespaced form (cross-store
# chunk-id collision fix); 0018 adds no table (conversation agent-config column);
# 0019 adds ``sync_config`` + ``sync_state`` for multi-machine sync (spec 010).
# The ``documents_fts_*`` shadow tables FTS5 creates under the hood are excluded
# — the assertions speak to the logical schema.
EXPECTED_TABLES = {
    "resources",
    "audit_log",
    "retention_policies",
    "mcp_capability_preferences",
    "mcp_invocations",
    "mcp_server_health",
    "skill_agent_bindings",
    "credentials",
    "documents",
    "chunks",
    "documents_fts",
    "memory_projection_bindings",
    "memory_store_project_roots",
    "embedding_config",
    "conversations",
    "chat_messages",
    "chat_models",
    "channel_peers",
    "sync_config",
    "sync_state",
}

# FTS5 creates these shadow tables for ``documents_fts``; they are an
# implementation detail of the virtual table, not schema the migrations name.
_FTS_SHADOW_PREFIX = "documents_fts_"

_ALEMBIC_INI = (
    pathlib.Path(__file__).resolve().parents[4]
    / "coffer"
    / "infrastructure"
    / "persistence"
    / "migrations"
    / "alembic.ini"
)


def _alembic_config() -> AlembicConfig:
    assert _ALEMBIC_INI.is_file(), f"alembic.ini not found at {_ALEMBIC_INI}"
    return AlembicConfig(str(_ALEMBIC_INI))


def _user_tables(db_path: pathlib.Path) -> set[str]:
    """Return the set of user-defined tables in the SQLite file.

    Excludes SQLite internal tables and Alembic's own bookkeeping table so the
    assertions speak only to schema owned by the migrations under test.
    """
    if not db_path.exists():
        return set()
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    finally:
        conn.close()
    return {
        name
        for (name,) in rows
        if name != "alembic_version" and not name.startswith(_FTS_SHADOW_PREFIX)
    }


def _alembic_version(db_path: pathlib.Path) -> str | None:
    conn = sqlite3.connect(str(db_path))
    try:
        try:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        except sqlite3.OperationalError:
            return None
    finally:
        conn.close()
    return row[0] if row else None


def test_migration_roundtrip_is_reversible_and_idempotent(tmp_path, monkeypatch):
    db_path = tmp_path / "roundtrip.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")

    cfg = _alembic_config()

    # 1. upgrade head -> full schema present, stamped at head.
    command.upgrade(cfg, "head")
    assert _user_tables(db_path) == EXPECTED_TABLES
    assert _alembic_version(db_path) == HEAD_REVISION

    # 2. downgrade base -> every downgrade() runs, all tables removed.
    command.downgrade(cfg, "base")
    assert _user_tables(db_path) == set()
    assert _alembic_version(db_path) is None

    # 3. upgrade head again -> round-trip is idempotent, schema restored.
    command.upgrade(cfg, "head")
    assert _user_tables(db_path) == EXPECTED_TABLES
    assert _alembic_version(db_path) == HEAD_REVISION


def test_migration_stepwise_downgrade_drops_per_revision_tables(tmp_path, monkeypatch):
    """Step the chain down one revision at a time and assert each downgrade()
    removes exactly the tables its matching upgrade() created."""
    db_path = tmp_path / "stepwise.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")

    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    assert _user_tables(db_path) == EXPECTED_TABLES

    # head (0020) -> 0016: drops sync_config + sync_state (spec 010); the
    # intervening 0017 (chunk-id rekey), 0018 (conversation agent-config
    # column) and 0020 (conversation-retention reset) add no tables.
    command.downgrade(cfg, "0016")
    assert "sync_config" not in _user_tables(db_path)
    assert "sync_state" not in _user_tables(db_path)

    # 0016 -> 0015: drops credentials (encrypted credential store).
    command.downgrade(cfg, "0015")
    assert "credentials" not in _user_tables(db_path)

    # 0013 added conversations.archived_at (spec 008 archive); it exists at head.
    with sqlite3.connect(db_path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(conversations)")}
    assert "archived_at" in cols

    # 0015 -> 0014: drops channel_peers (spec 009-channels).
    command.downgrade(cfg, "0014")
    assert "channel_peers" not in _user_tables(db_path)

    # 0013 -> 0012: drops conversations.archived_at (column-only, no table change).
    command.downgrade(cfg, "0012")
    with sqlite3.connect(db_path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(conversations)")}
    assert "archived_at" not in cols
    assert _user_tables(db_path) == EXPECTED_TABLES - {
        "credentials",
        "channel_peers",
        "sync_config",
        "sync_state",
    }

    # 0012 -> 0011: drops the chat tables (spec 008-agent-chat).
    command.downgrade(cfg, "0011")
    assert _user_tables(db_path) == EXPECTED_TABLES - {
        "credentials",
        "channel_peers",
        "sync_config",
        "sync_state",
        "conversations",
        "chat_messages",
        "chat_models",
    }

    # 0011 -> 0010: drops embedding_config (global embedding singleton).
    command.downgrade(cfg, "0010")
    assert "embedding_config" not in _user_tables(db_path)

    # 0009 -> 0008: drops memory_store_project_roots (spec 007-memory project root).
    command.downgrade(cfg, "0008")
    assert "memory_store_project_roots" not in _user_tables(db_path)

    # 0008 -> 0007: drops memory_projection_bindings (spec 007-memory projection).
    command.downgrade(cfg, "0007")
    assert "memory_projection_bindings" not in _user_tables(db_path)

    # 0007 -> 0006: memory reuses the unified substrate, so 0007 owns no table;
    # the unified schema stays present.
    command.downgrade(cfg, "0006")
    assert {"documents", "chunks", "documents_fts"} <= _user_tables(db_path)

    # 0006 -> 0005: drops the unified substrate (spec 006-knowledge-base).
    command.downgrade(cfg, "0005")
    tables_after_0005 = _user_tables(db_path)
    assert "documents" not in tables_after_0005
    assert "chunks" not in tables_after_0005
    assert "documents_fts" not in tables_after_0005

    # 0005 -> 0004: drops skill_agent_bindings (spec 005-skill-manager).
    command.downgrade(cfg, "0004")
    assert "skill_agent_bindings" not in _user_tables(db_path)

    # 0004 -> 0003: index-only revision, table set otherwise unchanged.
    command.downgrade(cfg, "0003")
    assert _user_tables(db_path) == EXPECTED_TABLES - {
        "credentials",
        "channel_peers",
        "sync_config",
        "sync_state",
        "embedding_config",
        "conversations",
        "chat_messages",
        "chat_models",
        "memory_store_project_roots",
        "memory_projection_bindings",
        "skill_agent_bindings",
        "documents",
        "chunks",
        "documents_fts",
    }

    # 0003 -> 0002: drops mcp_server_health.
    command.downgrade(cfg, "0002")
    assert "mcp_server_health" not in _user_tables(db_path)

    # 0002 -> 0001: drops the mcp_* tables created in 0002.
    command.downgrade(cfg, "0001")
    tables = _user_tables(db_path)
    assert "mcp_capability_preferences" not in tables
    assert "mcp_invocations" not in tables
    assert {"resources", "audit_log", "retention_policies"} <= tables

    # 0001 -> base: everything gone.
    command.downgrade(cfg, "base")
    assert _user_tables(db_path) == set()


def test_migration_0005_maps_legacy_skill_dir_to_config_dir(tmp_path, monkeypatch):
    """0005 rewrites agent config JSON: a legacy ``skill_dir`` override is
    mapped onto ``config_dir`` (not silently dropped), preserving where skills
    are delivered for upgraded installs."""
    db_path = tmp_path / "data.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    # Schema up to just before the skill migration.
    command.upgrade(cfg, "0004")

    # Seed a pre-005-skill-manager agent row carrying a legacy skill_dir override
    # (a `<dir>/skills` path) plus one with a non-standard override.
    conn = sqlite3.connect(str(db_path))
    try:
        for name, skill_dir in (("team", "/data/team/skills"), ("odd", "/data/custom")):
            conn.execute(
                "INSERT INTO resources (kind, name, config_json, enabled, created_at, updated_at)"
                " VALUES (?, ?, ?, 1, ?, ?)",
                (
                    "agent",
                    name,
                    json.dumps({"type": "claude_code", "skill_dir": skill_dir}),
                    "2026-05-20T00:00:00+00:00",
                    "2026-05-20T00:00:00+00:00",
                ),
            )
        conn.commit()
    finally:
        conn.close()

    # Apply 0005 (creates bindings table + rewrites agent config).
    command.upgrade(cfg, "0005")

    conn = sqlite3.connect(str(db_path))
    try:
        rows = dict(
            conn.execute("SELECT name, config_json FROM resources WHERE kind = 'agent'").fetchall()
        )
    finally:
        conn.close()
    team = json.loads(rows["team"])
    assert "skill_dir" not in team and team["config_dir"] == "/data/team"
    odd = json.loads(rows["odd"])
    assert "skill_dir" not in odd and odd["config_dir"] == "/data/custom"


def test_db_stamped_by_pre_redesign_branch_is_repaired(tmp_path, monkeypatch):
    """A DB that applied the PRE-redesign 0006/0007 (which created
    ``kb_documents``/``memory_records``) is stamped at 0007, so the in-place
    rewritten 0006 never re-runs and the unified ``documents`` schema is
    missing — every KB/memory write then 500s with "no such table: documents"
    (reproduced on a real install). ``upgrade head`` must repair such a DB:
    create the unified schema and drop the legacy tables."""
    db_path = tmp_path / "legacy.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    # Build the pre-redesign world: schema as of the OLD 0006/0007 — the 0005
    # baseline tables plus the legacy per-kind tables — stamped at 0007.
    command.upgrade(cfg, "0005")
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE kb_documents (id TEXT PRIMARY KEY, kb_name TEXT)")
        conn.execute("CREATE TABLE memory_records (id TEXT PRIMARY KEY, scope TEXT)")
        conn.execute("UPDATE alembic_version SET version_num = '0007'")
        conn.commit()
    finally:
        conn.close()

    command.upgrade(cfg, "head")

    tables = _user_tables(db_path)
    assert {"documents", "chunks", "documents_fts"} <= tables
    assert "kb_documents" not in tables
    assert "memory_records" not in tables
    assert _alembic_version(db_path) == HEAD_REVISION

    # And the repair is idempotent for fresh DBs: a second upgrade is a no-op.
    command.upgrade(cfg, "head")
    assert {"documents", "chunks", "documents_fts"} <= _user_tables(db_path)


def _seed_retention(db_path: pathlib.Path, table_name: str, retention_days: int | None) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO retention_policies "
            "(table_name, retention_days, last_pruned_at, last_pruned_rows, updated_at) "
            "VALUES (?, ?, ?, 0, ?)",
            (
                table_name,
                retention_days,
                "2026-05-01T00:00:00+00:00",  # a stale prune timestamp under old meaning
                "2026-05-01T00:00:00+00:00",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _retention_row(db_path: pathlib.Path, table_name: str):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            "SELECT retention_days, last_pruned_at, last_pruned_rows "
            "FROM retention_policies WHERE table_name = ?",
            (table_name,),
        ).fetchone()
    finally:
        conn.close()


def test_migration_0020_resets_legacy_single_stage_conversation_retention(tmp_path, monkeypatch):
    """A pre-two-stage install has a `conversations` retention row whose value
    meant "delete idle threads by updated_at" and NO `conversations_archive`
    row. After the flip to archived_at that row would be silently reinterpreted.
    0020 repairs it: resets `conversations` to the new delete default (30,
    measured by archived_at) and seeds the archive stage (7), and an ACTIVE
    thread (archived_at IS NULL) is never deleted under the new semantics."""
    db_path = tmp_path / "legacy_retention.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0019")
    # Legacy single-stage row: user had set "delete chats idle 14 days" (the old
    # updated_at meaning). No conversations_archive row exists yet.
    _seed_retention(db_path, "conversations", 14)
    # An active thread last touched long ago — under the OLD updated_at meaning
    # it was a delete candidate; under the NEW archived_at meaning it must not be.
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO conversations (id, agent_key, title, created_at, updated_at, archived_at) "
            "VALUES ('c-active', 'builtin', 'old active', "
            "'2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', NULL)"
        )
        conn.commit()
    finally:
        conn.close()

    command.upgrade(cfg, "head")

    conv = _retention_row(db_path, "conversations")
    archive = _retention_row(db_path, "conversations_archive")
    assert conv is not None and conv[0] == 30, "delete stage reset to the new default"
    assert conv[1] is None and conv[2] == 0, "stale prune bookkeeping cleared (clock changed)"
    assert archive is not None and archive[0] == 7, "archive stage seeded with its default"

    # Active threads (archived_at IS NULL) survive a delete-by-archived_at sweep.
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("DELETE FROM conversations WHERE archived_at < '2030-01-01T00:00:00+00:00'")
        conn.commit()
        survivors = {r[0] for r in conn.execute("SELECT id FROM conversations")}
    finally:
        conn.close()
    assert "c-active" in survivors, "an active conversation must not be mis-deleted on upgrade"


def test_migration_0020_keeps_disabled_conversation_retention_disabled(tmp_path, monkeypatch):
    """If the legacy install had conversation retention DISABLED (NULL), the
    upgrade must not silently re-enable deletion: both new stages stay NULL."""
    db_path = tmp_path / "disabled_retention.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0019")
    _seed_retention(db_path, "conversations", None)  # disabled

    command.upgrade(cfg, "head")

    conv = _retention_row(db_path, "conversations")
    archive = _retention_row(db_path, "conversations_archive")
    assert conv is not None and conv[0] is None, "delete stage stays disabled"
    assert archive is not None and archive[0] is None, "archive stage seeded disabled too"


def test_migration_0020_is_noop_when_already_two_stage(tmp_path, monkeypatch):
    """An install already on the two-stage model (both rows present, possibly
    user-customised) must be left untouched — no clobbering of a deliberate
    value."""
    db_path = tmp_path / "two_stage.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "0019")
    _seed_retention(db_path, "conversations", 45)  # custom new-semantics value
    _seed_retention(db_path, "conversations_archive", 10)

    command.upgrade(cfg, "head")

    assert _retention_row(db_path, "conversations")[0] == 45, "custom delete value preserved"
    assert _retention_row(db_path, "conversations_archive")[0] == 10, "custom archive value kept"


def test_migration_0020_is_noop_on_fresh_db_with_no_retention_rows(tmp_path, monkeypatch):
    """Retention rows are seeded at runtime, not by migrations — so on a fresh
    `upgrade head` 0020 finds no `conversations` row and does nothing (no crash,
    no spurious rows)."""
    db_path = tmp_path / "fresh.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    command.upgrade(cfg, "head")

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM retention_policies").fetchone()[0]
    finally:
        conn.close()
    assert count == 0, "no retention rows are conjured on a fresh install"


def test_migration_0017_rekeys_chunk_ids_per_store(tmp_path, monkeypatch):
    """0017 rewrites pre-existing bare ``'<doc-id>:<position>'`` chunk ids to
    the per-store namespaced ``'<digest>:<doc-id>:<position>'`` form, in both
    ``chunks.id`` and ``documents_fts.chunk_id`` (keeping the FTS text), and is
    idempotent — a re-run must not double the prefix."""
    import hashlib

    db_path = tmp_path / "rekey.db"
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{db_path}")
    cfg = _alembic_config()

    # Schema as of just before the rekey, seeded with old-format rows for two
    # stores (distinct doc ids — the old single-column PK could not even hold
    # the colliding case; that data was already lost and reindex rebuilds it).
    command.upgrade(cfg, "0016")
    conn = sqlite3.connect(str(db_path))
    try:
        for doc_id, store, chunk_text in (("d1", "kb1", "alpha"), ("d2", "kb2", "beta")):
            conn.execute(
                "INSERT INTO chunks (id, document_id, kind, resource_name, position)"
                " VALUES (?, ?, 'knowledge_base', ?, 0)",
                (f"{doc_id}:0", doc_id, store),
            )
            conn.execute(
                "INSERT INTO documents_fts (text, resource_name, chunk_id) VALUES (?, ?, ?)",
                (chunk_text, store, f"{doc_id}:0"),
            )
        conn.commit()
    finally:
        conn.close()

    command.upgrade(cfg, "head")

    def _scope(store: str) -> str:
        # Mirrors store_scope in coffer/infrastructure/knowledge/sqlite_index.py.
        return hashlib.sha1(f"knowledge_base\x00{store}".encode()).hexdigest()[:12]

    expected = {f"{_scope('kb1')}:d1:0", f"{_scope('kb2')}:d2:0"}
    conn = sqlite3.connect(str(db_path))
    try:
        chunk_ids = {r[0] for r in conn.execute("SELECT id FROM chunks")}
        fts_rows = dict(conn.execute("SELECT chunk_id, text FROM documents_fts").fetchall())
    finally:
        conn.close()
    assert chunk_ids == expected
    assert set(fts_rows) == expected  # FTS rows follow their chunks rows
    assert fts_rows[f"{_scope('kb1')}:d1:0"] == "alpha"  # text survives the rekey

    # Idempotent: re-running 0017 (stamp back + upgrade) must not re-prefix.
    command.stamp(cfg, "0016")
    command.upgrade(cfg, "head")
    conn = sqlite3.connect(str(db_path))
    try:
        assert {r[0] for r in conn.execute("SELECT id FROM chunks")} == expected
    finally:
        conn.close()
