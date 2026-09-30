"""The database becomes ``runs.db``: history only, keyed by uid.

The vault layout (ADR storage-is-five-classes-by-nature) moves everything
that is not history out of the database — resources become files; reach,
custom tools' reach overrides and retention local JSON; credentials ciphertext
files; the MCP capability switches, channel pairings and engine settings vault
documents; health and skill deliveries ``derived.db``. The pre-layout hooks the migration runner
calls between 0116 and this revision have already written those files from
these tables; this revision is the database's half of the move:

1. The four history tables that pointed at ``resources.id`` —
   ``audit_log``, ``channel_thread_conversations``, ``channel_thread_history``,
   ``channel_outbox`` — are rebuilt with ``resource_uid`` in its place, filled
   by joining ``resources.id`` to ``resources.uid``, their foreign keys gone
   (there is no table left to point at) and their indexes recreated on the uid.
   An audit row whose resource was deleted keeps its label and names no uid;
   a channel row always had its channel (the foreign key cascaded).
2. Every table whose state moved out is dropped, ``resources`` last.
3. Sync (ADR sync-applies-clean-merges-and-stops-on-any-conflict): the remote
   row moved to ``local/sync/remote.json`` before this revision; the
   convergence pointer is the vault repository's ``HEAD`` and the retry set
   has no successor, so ``sync_remotes``, ``sync_convergence_state`` and
   ``sync_held_paths`` are dropped. ``sync_runs`` stays with its columns, and
   its rows go: their payloads describe rounds of the retired translation
   layer, in a shape the new round record does not read.

Downgrade recreates the dropped tables empty and puts integer columns back,
NULL where the audit trail cannot be mapped back and without the channel rows
(their channel's row number no longer exists): it keeps the chain reversible
for the migration tests, not the data.

Revision ID: 0136
Revises: 0116
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0136"
down_revision: str | None = "0116"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Child tables before ``resources``: nothing may still reference it.
_DROPPED = (
    "mcp_capability_preferences",
    "mcp_tool_reach",
    "channel_peers",
    "skill_source_status",
    "skill_agent_bindings",
    "mcp_server_health",
    "credentials",
    "secret_bindings",
    "secret_approvals",
    "secret_boundary_settings",
    "internal_engine_config",
    "retention_policies",
    "sync_remotes",
    "sync_convergence_state",
    "sync_held_paths",
    "resources",
)

_AUDIT = """
CREATE TABLE audit_log__new (
    id INTEGER NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    event_type VARCHAR NOT NULL,
    resource_kind VARCHAR,
    resource_name VARCHAR,
    actor VARCHAR NOT NULL,
    details_json TEXT,
    resource_uid VARCHAR,
    PRIMARY KEY (id)
)"""
_AUDIT_COPY = """
INSERT INTO audit_log__new
    (id, timestamp, event_type, resource_kind, resource_name, actor, details_json, resource_uid)
SELECT a.id, a.timestamp, a.event_type, a.resource_kind, a.resource_name, a.actor,
       a.details_json, r.uid
FROM audit_log a LEFT JOIN resources r ON r.id = a.resource_id"""
_AUDIT_INDEXES = (
    "CREATE INDEX idx_audit_resource ON audit_log (resource_kind, resource_name, timestamp DESC)",
    "CREATE INDEX idx_audit_time ON audit_log (timestamp DESC)",
    "CREATE INDEX idx_audit_eventtype ON audit_log (event_type, timestamp DESC)",
    "CREATE INDEX idx_audit_resource_uid ON audit_log (resource_uid, timestamp)",
)

_THREADS = """
CREATE TABLE channel_thread_conversations__new (
    id INTEGER NOT NULL,
    resource_uid VARCHAR NOT NULL,
    chat_id VARCHAR NOT NULL,
    thread_id VARCHAR DEFAULT '' NOT NULL,
    active_conversation_id VARCHAR,
    preferred_agent VARCHAR,
    updated_at TIMESTAMP NOT NULL,
    parallel_ordinal INTEGER,
    parallel_title TEXT,
    chat_kind VARCHAR,
    preferred_model VARCHAR,
    preferred_effort VARCHAR,
    preferred_cwd TEXT,
    PRIMARY KEY (id),
    CONSTRAINT uq_channel_thread_conv_resource_chat_thread UNIQUE (resource_uid, chat_id, thread_id)
)"""
_THREADS_COLUMNS = (
    "chat_id, thread_id, active_conversation_id, preferred_agent, updated_at, "
    "parallel_ordinal, parallel_title, chat_kind, preferred_model, preferred_effort, preferred_cwd"
)
_THREADS_INDEXES = (
    "CREATE INDEX idx_channel_thread_conv_resource ON channel_thread_conversations (resource_uid)",
)

_HISTORY = """
CREATE TABLE channel_thread_history__new (
    id INTEGER NOT NULL,
    resource_uid VARCHAR NOT NULL,
    chat_id VARCHAR NOT NULL,
    thread_id VARCHAR DEFAULT '' NOT NULL,
    conversation_id VARCHAR NOT NULL,
    chat_kind VARCHAR,
    opened_at TIMESTAMP NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_channel_thread_history_conversation UNIQUE (conversation_id)
)"""
_HISTORY_COLUMNS = "chat_id, thread_id, conversation_id, chat_kind, opened_at"
_HISTORY_INDEXES = (
    "CREATE INDEX idx_channel_thread_history_thread"
    " ON channel_thread_history (resource_uid, chat_id, thread_id)",
)

_OUTBOX = """
CREATE TABLE channel_outbox__new (
    id INTEGER NOT NULL,
    resource_uid VARCHAR NOT NULL,
    chat_id VARCHAR NOT NULL,
    thread_id VARCHAR DEFAULT '' NOT NULL,
    chat_kind VARCHAR NOT NULL,
    conversation_id VARCHAR NOT NULL,
    kind VARCHAR NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    delivered_at TIMESTAMP,
    PRIMARY KEY (id)
)"""
_OUTBOX_COLUMNS = (
    "chat_id, thread_id, chat_kind, conversation_id, kind, text, created_at, delivered_at"
)
_OUTBOX_INDEXES = (
    "CREATE INDEX idx_channel_outbox_pending ON channel_outbox (resource_uid, delivered_at)",
    "CREATE INDEX idx_channel_outbox_conversation ON channel_outbox (conversation_id)",
)


def _swap(table: str, indexes: Sequence[str]) -> None:
    op.execute(f"DROP TABLE {table}")
    op.execute(f"ALTER TABLE {table}__new RENAME TO {table}")
    for ddl in indexes:
        op.execute(ddl)


def _rekey_channel_table(table: str, create: str, columns: str, indexes: Sequence[str]) -> None:
    op.execute(create)
    op.execute(
        f"INSERT INTO {table}__new (id, resource_uid, {columns}) "
        f"SELECT t.id, r.uid, {', '.join('t.' + c.strip() for c in columns.split(','))} "
        f"FROM {table} t JOIN resources r ON r.id = t.resource_id"
    )
    _swap(table, indexes)


def upgrade() -> None:
    op.execute(_AUDIT)
    op.execute(_AUDIT_COPY)
    _swap("audit_log", _AUDIT_INDEXES)
    _rekey_channel_table(
        "channel_thread_conversations", _THREADS, _THREADS_COLUMNS, _THREADS_INDEXES
    )
    _rekey_channel_table("channel_thread_history", _HISTORY, _HISTORY_COLUMNS, _HISTORY_INDEXES)
    _rekey_channel_table("channel_outbox", _OUTBOX, _OUTBOX_COLUMNS, _OUTBOX_INDEXES)
    for table in _DROPPED:
        op.execute(f"DROP TABLE IF EXISTS {table}")
    op.execute("DELETE FROM sync_runs")


# --- downgrade: the 0116 shape, empty ------------------------------------------

_RECREATE = (
    """CREATE TABLE resources (
    id INTEGER NOT NULL, kind VARCHAR NOT NULL, name VARCHAR NOT NULL, description TEXT,
    config_json TEXT NOT NULL, enabled BOOLEAN DEFAULT 1 NOT NULL,
    created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL, scope_json TEXT,
    uid VARCHAR, title VARCHAR(80), rev INTEGER DEFAULT '1' NOT NULL,
    PRIMARY KEY (id), CONSTRAINT uq_resources_kind_name UNIQUE (kind, name))""",
    "CREATE INDEX idx_resources_kind_enabled ON resources (kind, enabled)",
    "CREATE UNIQUE INDEX ux_provider_single_internal_default ON resources (kind) WHERE "
    "kind = 'provider' AND json_extract(config_json, '$.internal_default') = 1",
    "CREATE UNIQUE INDEX ux_provider_single_transcribe_default ON resources (kind) WHERE "
    "kind = 'provider' AND json_extract(config_json, '$.transcribe_default') = 1",
    "CREATE UNIQUE INDEX uq_resources_uid ON resources (uid)",
    """CREATE TABLE credentials (ref VARCHAR NOT NULL, ciphertext BLOB NOT NULL,
    created_at VARCHAR NOT NULL, updated_at VARCHAR NOT NULL, PRIMARY KEY (ref))""",
    """CREATE TABLE secret_bindings (ref VARCHAR NOT NULL, destination_kind VARCHAR NOT NULL,
    destination_uid VARCHAR NOT NULL, slot VARCHAR NOT NULL, target_fingerprint VARCHAR NOT NULL,
    approved_at VARCHAR NOT NULL, approval_id VARCHAR,
    PRIMARY KEY (ref, destination_kind, destination_uid, slot))""",
    """CREATE TABLE secret_approvals (id VARCHAR NOT NULL, op VARCHAR NOT NULL,
    status VARCHAR NOT NULL, created_at VARCHAR NOT NULL, requested_by VARCHAR NOT NULL,
    ref VARCHAR, destination_kind VARCHAR, destination_uid VARCHAR, destination_label VARCHAR,
    slot VARCHAR, target TEXT, target_fingerprint VARCHAR, pending_ciphertext BLOB,
    decided_at VARCHAR, decided_by VARCHAR, PRIMARY KEY (id))""",
    "CREATE INDEX idx_secret_approvals_status ON secret_approvals (status)",
    """CREATE TABLE secret_boundary_settings ("key" VARCHAR NOT NULL, value VARCHAR NOT NULL,
    PRIMARY KEY ("key"))""",
    """CREATE TABLE mcp_capability_preferences (id INTEGER NOT NULL,
    resource_id INTEGER NOT NULL, capability_type VARCHAR NOT NULL,
    capability_key VARCHAR NOT NULL, enabled BOOLEAN DEFAULT 1 NOT NULL,
    first_seen_at TIMESTAMP NOT NULL, last_seen_at TIMESTAMP NOT NULL, PRIMARY KEY (id),
    CONSTRAINT uq_mcp_prefs_resource_type_key UNIQUE (resource_id, capability_type, capability_key),
    FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE)""",
    "CREATE INDEX idx_prefs_resource ON mcp_capability_preferences"
    " (resource_id, capability_type, enabled)",
    """CREATE TABLE channel_peers (id INTEGER NOT NULL, resource_id INTEGER NOT NULL,
    chat_id VARCHAR NOT NULL, display_name VARCHAR DEFAULT '' NOT NULL,
    paired_at TIMESTAMP NOT NULL, sender_id VARCHAR, PRIMARY KEY (id),
    CONSTRAINT uq_channel_peers_resource_chat UNIQUE (resource_id, chat_id),
    FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE)""",
    "CREATE INDEX idx_channel_peers_resource ON channel_peers (resource_id)",
    """CREATE TABLE internal_engine_config (id INTEGER NOT NULL, model VARCHAR,
    updated_at TIMESTAMP NOT NULL, auto_curate_enabled BOOLEAN DEFAULT 1 NOT NULL,
    curate_owner_machine_id VARCHAR, auto_aggregate_enabled BOOLEAN DEFAULT 1 NOT NULL,
    aggregate_interval_s INTEGER, auto_distil_enabled BOOLEAN DEFAULT 1 NOT NULL,
    distil_interval_s INTEGER, curate_interval_s INTEGER, model_timeout_s INTEGER,
    transcribe_model VARCHAR, CONSTRAINT pk_internal_engine_config PRIMARY KEY (id),
    CONSTRAINT ck_internal_engine_config_singleton CHECK (id = 1))""",
    """CREATE TABLE retention_policies (table_name VARCHAR NOT NULL, retention_days INTEGER,
    last_pruned_at TIMESTAMP, last_pruned_rows INTEGER DEFAULT 0 NOT NULL,
    updated_at TIMESTAMP NOT NULL, PRIMARY KEY (table_name),
    CONSTRAINT ck_retention_positive_or_null
        CHECK (retention_days IS NULL OR retention_days > 0))""",
    """CREATE TABLE skill_source_status (skill_resource_id INTEGER NOT NULL,
    checked_at TIMESTAMP, last_success_at TIMESTAMP, error TEXT, latest_commit VARCHAR,
    commits_ahead INTEGER DEFAULT '0' NOT NULL, files_changed INTEGER DEFAULT '0' NOT NULL,
    dismissed_commit VARCHAR, PRIMARY KEY (skill_resource_id),
    FOREIGN KEY(skill_resource_id) REFERENCES resources (id) ON DELETE CASCADE)""",
    """CREATE TABLE skill_agent_bindings (skill_resource_id INTEGER NOT NULL,
    agent_resource_id INTEGER NOT NULL, enabled BOOLEAN DEFAULT 0 NOT NULL,
    last_linked_at TIMESTAMP, last_link_path TEXT, link_mode VARCHAR,
    CONSTRAINT pk_skill_agent_bindings PRIMARY KEY (skill_resource_id, agent_resource_id),
    FOREIGN KEY(skill_resource_id) REFERENCES resources (id) ON DELETE CASCADE,
    FOREIGN KEY(agent_resource_id) REFERENCES resources (id) ON DELETE CASCADE)""",
    "CREATE INDEX idx_bindings_agent ON skill_agent_bindings (agent_resource_id, enabled)",
    "CREATE INDEX idx_bindings_skill ON skill_agent_bindings (skill_resource_id, enabled)",
    """CREATE TABLE mcp_server_health (resource_uid VARCHAR NOT NULL, status VARCHAR NOT NULL,
    checked_at TIMESTAMP NOT NULL, PRIMARY KEY (resource_uid))""",
    """CREATE TABLE mcp_tool_reach (resource_uid VARCHAR NOT NULL, tool VARCHAR NOT NULL,
    agents_json TEXT NOT NULL, updated_at TIMESTAMP NOT NULL, PRIMARY KEY (resource_uid, tool))""",
    """CREATE TABLE sync_remotes (id INTEGER NOT NULL, url VARCHAR NOT NULL,
    branch VARCHAR DEFAULT 'main' NOT NULL, credential_ref VARCHAR,
    include_credentials BOOLEAN DEFAULT 0 NOT NULL,
    interval_seconds INTEGER DEFAULT '3600' NOT NULL,
    enabled BOOLEAN DEFAULT 1 NOT NULL, worktree_path VARCHAR DEFAULT '~/.coffer/sync' NOT NULL,
    last_run_at TIMESTAMP, last_status VARCHAR, last_error VARCHAR, last_commit VARCHAR,
    updated_at TIMESTAMP NOT NULL, last_started_at TIMESTAMP, last_join VARCHAR,
    last_run_json TEXT, PRIMARY KEY (id),
    CONSTRAINT ck_sync_remote_single_row CHECK (id = 1),
    CONSTRAINT ck_sync_remote_interval_positive CHECK (interval_seconds > 0))""",
    """CREATE TABLE sync_convergence_state (id INTEGER NOT NULL, pointer VARCHAR,
    pending_json TEXT, updated_at TIMESTAMP NOT NULL, PRIMARY KEY (id),
    CONSTRAINT ck_convergence_state_single_row CHECK (id = 1))""",
    """CREATE TABLE sync_held_paths (path VARCHAR NOT NULL, applicable BOOLEAN DEFAULT 1 NOT NULL,
    held_at TIMESTAMP NOT NULL, PRIMARY KEY (path))""",
)


def _to_integer(table: str, create_uid_ddl: str, columns: str, indexes: Sequence[str]) -> None:
    create = (
        create_uid_ddl.replace(f"{table}__new", f"{table}__old")
        .replace("resource_uid VARCHAR NOT NULL", "resource_id INTEGER NOT NULL")
        .replace("resource_uid VARCHAR", "resource_id INTEGER")
        .replace("UNIQUE (resource_uid", "UNIQUE (resource_id")
    )
    op.execute(create)
    if table == "audit_log":
        op.execute(f"INSERT INTO {table}__old (id, {columns}) SELECT id, {columns} FROM {table}")
    op.execute(f"DROP TABLE {table}")
    op.execute(f"ALTER TABLE {table}__old RENAME TO {table}")
    for ddl in indexes:
        op.execute(ddl.replace("resource_uid", "resource_id"))


def downgrade() -> None:
    for ddl in _RECREATE:
        op.execute(ddl)
    _to_integer(
        "audit_log",
        _AUDIT,
        "timestamp, event_type, resource_kind, resource_name, actor, details_json",
        tuple(i.replace("idx_audit_resource_uid", "idx_audit_resource_id") for i in _AUDIT_INDEXES),
    )
    _to_integer("channel_thread_conversations", _THREADS, _THREADS_COLUMNS, _THREADS_INDEXES)
    _to_integer("channel_thread_history", _HISTORY, _HISTORY_COLUMNS, _HISTORY_INDEXES)
    _to_integer("channel_outbox", _OUTBOX, _OUTBOX_COLUMNS, _OUTBOX_INDEXES)
