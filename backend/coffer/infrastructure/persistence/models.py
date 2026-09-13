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
    #: The resource's stable row id; kind+name are the label it carried then.
    resource_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resource_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    resource_name: Mapped[str | None] = mapped_column(String, nullable=True)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_audit_resource", "resource_kind", "resource_name", "timestamp"),
        Index("idx_audit_resource_id", "resource_id", "timestamp"),
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
    """The one sync remote, and the last converge round against it (spec vault-sync).

    Single row by construction: ``id`` is pinned to 1 by a check constraint, so
    "at most one sync remote" is a schema fact rather than a convention the
    application has to remember. ``credential_ref`` holds a reference into the
    credential store — never a secret, so this row is safe to read into an API
    response or a log line without redaction.

    The ``last_*`` columns describe the most recent round rather than a
    history: what a user needs from it is whether it worked and what to do
    next, and the git history on the remote is the real record of what changed.
    The scalar columns are the ones a status surface reads directly; everything
    else a ``ConvergeRun`` carries — the two diff summaries, the conflicted and
    agent-resolved paths, the per-path failures, the locked refs and any held
    confirmation — lives in ``last_run_json`` and is stored exactly once, so
    the two can never disagree.
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
    last_started_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String, nullable=True)
    last_join: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    last_commit: Mapped[str | None] = mapped_column(String, nullable=True)
    last_run_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_sync_remote_single_row"),
        CheckConstraint("interval_seconds > 0", name="ck_sync_remote_interval_positive"),
    )


class ConvergenceStateModel(Base):
    """This machine's convergence pointer and any held confirmation.

    Machine-local and **never synced** (spec vault-sync ``## What does not
    sync``): ``coffer.db`` is excluded from the bundle, which is most of why
    this state belongs in SQLite rather than beside the working tree. A pointer
    that travelled would be a different machine's claim about what this vault
    has absorbed, and the whole diff-based apply rests on it being this one's.

    Single row, pinned the same way the remote is.
    """

    __tablename__ = "sync_convergence_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    #: The commit this vault has provably absorbed; NULL means "joining".
    pointer: Mapped[str | None] = mapped_column(String, nullable=True)
    #: The round the deletion guard is holding, serialized. Held rather than
    #: re-derived: the round had already merged, and possibly had an agent
    #: resolve conflicts, by the time the guard tripped.
    pending_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (CheckConstraint("id = 1", name="ck_convergence_state_single_row"),)


class SyncHeldPathModel(Base):
    """One path the export must not publish as a deletion (spec vault-sync).

    Two sets in one table, told apart by ``applicable``. A path the vault
    failed to absorb is *pending*: retried next round, reported as an error,
    released on success. A path that cannot apply on this machine at all — an
    ``agent`` whose ``config_dir`` does not exist here — is *not applicable*:
    preserved identically, but never retried and never reported, because a
    fact about this machine should not become an error the user learns to
    ignore.

    Either way the exporter must leave the path in the working tree. Deleting
    it would turn "this vault could not absorb it" into "the user deleted it",
    which is the confusion the whole design exists to prevent.
    """

    __tablename__ = "sync_held_paths"

    path: Mapped[str] = mapped_column(String, primary_key=True)
    applicable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    held_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class CredentialModel(Base):
    """Fernet-encrypted secret values. Plaintext NEVER lands in this table —
    only ciphertext produced by EncryptedCredentialStore. Timestamps are ISO-8601
    strings written by the sync store (stdlib sqlite3, not the async ORM)."""

    __tablename__ = "credentials"

    ref: Mapped[str] = mapped_column(String, primary_key=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class InternalEngineConfigModel(Base):
    """The single, global internal-engine model selection (one row, ``id`` = 1).

    The internal engine takes its endpoint + key from the ``internal_default``
    connection; only the model is stored here (spec provider-switching amendment 2026-06-22b)."""

    __tablename__ = "internal_engine_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    #: Whether the background tidy worker may run (spec knowledge FR-051).
    auto_tidy_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: The one machine allowed to run the unattended tidy pass once a vault
    #: spans several (spec vault-sync ``## Unattended rewriters``). NULL means
    #: "wherever this is read", which is correct for a single-machine vault.
    tidy_owner_machine_id: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)

    __table_args__ = (CheckConstraint("id = 1", name="ck_internal_engine_config_singleton"),)


class MemoryOverrideModel(Base):
    """The developer's decisions about one fact — the one non-derived state
    the memory layer holds (spec memory FR-040, FR-070; ADR
    ``aggregate-agent-memory-never-write-it``).

    Everything else under ``~/.coffer/memory/`` is a file that aggregation can
    delete and rebuild; a hide, a pin, a hand-picked supersession or a settled
    conflict cannot be recomputed, so this is the one table this layer is
    allowed to add. Keyed by ``fact_key`` (``Fact.key``) rather than a
    surrogate id, because that key is built to survive recomputation — a
    rebuild that renames every file must still find this row.
    """

    __tablename__ = "memory_overrides"

    fact_key: Mapped[str] = mapped_column(String, primary_key=True)
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    superseded_by: Mapped[str] = mapped_column(String, nullable=False, default="")
    conflict_choice: Mapped[str] = mapped_column(String, nullable=False, default="")
    #: Who last set this override — kept on the row itself so the decision is
    #: attributable even before a caller wires up the shared audit log.
    actor: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
