"""SQLAlchemy ORM models for the kind-agnostic tables of ``runs.db``.

``runs.db`` holds history only (ADR storage-is-five-classes-by-nature):
resources are files, reach and retention are local JSON, derived tables are in
``derived.db``. Kind-specific history tables live in each kind's
``infrastructure/<kind>/`` package and register against the same
``Base.metadata`` so Alembic discovers them in one place.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base


class AuditLogModel(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    #: The resource's uid; kind+name are the label it
    #: carried then.
    resource_uid: Mapped[str | None] = mapped_column(String, nullable=True)
    resource_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    resource_name: Mapped[str | None] = mapped_column(String, nullable=True)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Correlation ids; see ``domain.audit.AuditEntry``.
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    turn_id: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("idx_audit_trace", "trace_id"),
        Index("idx_audit_resource", "resource_kind", "resource_name", "timestamp"),
        Index("idx_audit_resource_uid", "resource_uid", "timestamp"),
        Index("idx_audit_time", "timestamp"),
        Index("idx_audit_eventtype", "event_type", "timestamp"),
    )


class SyncRunModel(Base):
    """Every sync round this machine has run (spec vault-sync; ADR
    sync-applies-clean-merges-and-stops-on-any-conflict).

    Machine-local: a history that travelled would be another machine's
    account of rounds this one never ran. The columns are what a list reads at
    a glance; everything else a ``RoundRecord`` carries is ``payload_json``,
    written once. Swept by the retention worker (``sync_runs``).
    """

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    #: ``new`` / ``returning`` when this round joined a remote; NULL otherwise.
    join_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    #: ``commit`` is reserved in SQL, so the column says what it holds instead.
    commit_sha: Mapped[str | None] = mapped_column(String, nullable=True)
    #: Already redacted of the push secret by the time it arrives here.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # The history is always read newest-first and pruned oldest-first;
        # both are this index.
        Index("ix_sync_runs_finished_at", "finished_at"),
    )


# The usage-metering tables live in their own module to keep
# this one within the file-size budget; importing it here registers them on
# ``Base.metadata`` wherever the core models are loaded (``create_all``,
# Alembic's env.py).
# The ignored attention items, registered the same way.
from coffer.infrastructure.persistence import (  # noqa: E402, F401
    attention_ignore_repo as _attention_ignore_repo,
)
from coffer.infrastructure.persistence import usage_models as _usage_models  # noqa: E402, F401
