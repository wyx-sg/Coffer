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


class CredentialModel(Base):
    """Fernet-encrypted secret values. Plaintext NEVER lands in this table —
    only ciphertext produced by EncryptedCredentialStore. Timestamps are ISO-8601
    strings written by the sync store (stdlib sqlite3, not the async ORM)."""

    __tablename__ = "credentials"

    ref: Mapped[str] = mapped_column(String, primary_key=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class DistilledSessionModel(Base):
    """Machine-local idempotency ledger for the auto-distill catch-up sweep
    (Spec 007 FR-046).

    One row per ``(agent_name, session_id, content_sha256)`` proves that exact
    session content was already distilled into the journal lane, so the sweep
    never double-distills a settled session. A material content change yields a
    new ``content_sha256`` and is therefore eligible to re-distill. This ledger
    is the idempotency key the future SessionEnd hook (slice 6) will share.
    """

    __tablename__ = "distilled_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String, nullable=False)
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String, nullable=False)
    distilled_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "agent_name",
            "session_id",
            "content_sha256",
            name="uq_distilled_sessions_agent_session_sha",
        ),
    )


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
    connection; only the model is stored here (spec 011 amendment 2026-06-22b)."""

    __tablename__ = "internal_engine_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (CheckConstraint("id = 1", name="ck_internal_engine_config_singleton"),)
