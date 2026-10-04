"""audit rows and MCP invocations carry the correlation id

The audit log, the MCP invocation log and the daemon log could not be joined:
the daemon log carried a ``trace_id``, the invocation log only the MCP session
id, and the audit row neither (spec resource-framework "Correlate the audit
log, the MCP invocation log and the daemon log by one trace id").

* ``audit_log`` gains ``trace_id`` — the HTTP request's or the turn's id —
  and ``conversation_id`` / ``turn_id`` for a row a chat or channel turn wrote,
  with an index on ``trace_id`` for the "everything this request did" read.
* ``mcp_invocations`` gains ``trace_id``, indexed the same way.

All nullable, and NULL on every row written before this revision: those rows
were never correlated, and inventing an id for them would join them to nothing
or to the wrong thing.

Revision ID: 0137
Revises: 0136
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0137"
down_revision: str | None = "0136"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUDIT_COLUMNS = ("trace_id", "conversation_id", "turn_id")


def upgrade() -> None:
    with op.batch_alter_table("audit_log") as batch:
        for column in _AUDIT_COLUMNS:
            batch.add_column(sa.Column(column, sa.String(), nullable=True))
    op.create_index("idx_audit_trace", "audit_log", ["trace_id"])
    op.add_column("mcp_invocations", sa.Column("trace_id", sa.String(), nullable=True))
    op.create_index("idx_invocations_trace", "mcp_invocations", ["trace_id"])


def downgrade() -> None:
    op.drop_index("idx_invocations_trace", table_name="mcp_invocations")
    with op.batch_alter_table("mcp_invocations") as batch:
        batch.drop_column("trace_id")
    op.drop_index("idx_audit_trace", table_name="audit_log")
    with op.batch_alter_table("audit_log") as batch:
        for column in reversed(_AUDIT_COLUMNS):
            batch.drop_column(column)
