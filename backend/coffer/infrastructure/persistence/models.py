"""SQLAlchemy ORM models for the kind-agnostic core tables.

Resources, audit_log, and retention_policies. Kind-specific tables live
in `coffer.infrastructure.mcp.persistence` (or wherever the kind lands)
and register against the same `Base.metadata` so Alembic discovers them
in one place.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base


class ResourceModel(Base):
    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    # Framework-level per-agent activation scope (ADR per-agent-resource-scope): a JSON list of
    # agent names; NULL means unscoped. Added by migration 0046.
    scope_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("kind", "name", name="uq_resources_kind_name"),
        Index("idx_resources_kind_enabled", "kind", "enabled"),
    )


class AuditLogModel(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    resource_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    resource_name: Mapped[str | None] = mapped_column(String, nullable=True)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_audit_resource", "resource_kind", "resource_name", "timestamp"),
        Index("idx_audit_time", "timestamp"),
        Index("idx_audit_eventtype", "event_type", "timestamp"),
    )


class RetentionPolicyModel(Base):
    __tablename__ = "retention_policies"

    table_name: Mapped[str] = mapped_column(String, primary_key=True)
    retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_pruned_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_pruned_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "retention_days IS NULL OR retention_days > 0",
            name="ck_retention_positive_or_null",
        ),
    )


class SyncRemoteModel(Base):
    """The one backup remote (spec vault-export-import ``## Backup``).

    Single row by construction: ``id`` is pinned to 1 by a check constraint, so
    "at most one backup remote" is a schema fact rather than a convention the
    application has to remember. ``credential_ref`` holds a reference into the
    credential store — never a secret, so this row is safe to read into an API
    response or a log line without redaction.

    The ``last_*`` columns describe the most recent run rather than a history:
    what a user needs from the last run is whether it worked and what to do
    next, and the git history on the remote is the real record of what changed.
    """

    __tablename__ = "sync_remotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    url: Mapped[str] = mapped_column(String, nullable=False)
    branch: Mapped[str] = mapped_column(String, nullable=False, default="main")
    credential_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    include_credentials: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    worktree_path: Mapped[str] = mapped_column(String, nullable=False, default="~/.coffer/sync")
    last_run_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    last_commit: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_sync_remote_single_row"),
        CheckConstraint("interval_seconds > 0", name="ck_sync_remote_interval_positive"),
    )


class CredentialModel(Base):
    """Fernet-encrypted secret values. Plaintext NEVER lands in this table —
    only ciphertext produced by EncryptedCredentialStore. Timestamps are ISO-8601
    strings written by the sync store (stdlib sqlite3, not the async ORM)."""

    __tablename__ = "credentials"

    ref: Mapped[str] = mapped_column(String, primary_key=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class EmbeddingConfigModel(Base):
    """The single, global embedding configuration (one row, ``id`` pinned to 1).

    Embedding is installation-wide, not per-resource: every KB and memory store
    that enables vector retrieval shares this config."""

    __tablename__ = "embedding_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    base_url: Mapped[str | None] = mapped_column(String, nullable=True)
    credential_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False, default=768)
    default_chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=512)
    default_chunk_overlap: Mapped[int] = mapped_column(Integer, nullable=False, default=64)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (CheckConstraint("id = 1", name="ck_embedding_config_singleton"),)


class InternalEngineConfigModel(Base):
    """The single, global internal-engine model selection (one row, ``id`` = 1).

    The internal engine takes its endpoint + key from the ``internal_default``
    connection; only the model is stored here (spec provider-switching amendment 2026-06-22b)."""

    __tablename__ = "internal_engine_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (CheckConstraint("id = 1", name="ck_internal_engine_config_singleton"),)
