"""drop audit rows whose event type no longer exists

The simplification pass cut the audit enum from 66 members to 39, on the rule
that the log records *decisions and changes a person or agent made*, not
telemetry a table already answers. The code stopped writing the retired 27 the
moment they left the enum — but the rows already in `audit_log` stayed, and one
of them dominates the table: `journal_append` was 98.5% of it (4318 of 4384
rows) on the vault this was measured against, recording only a `char_size` for
content that lives in the journal files themselves.

Retention would eventually age them out, but "eventually" is the wrong answer
for two reasons. `coffer__diagnose` hands an agent a window of this table when
something has gone wrong with Coffer; a window that is 98% one retired
bookkeeping event is a window that shows nothing. And the retired rows carry
event types nothing in the code can name any more, so anything reading the
table has to cope with values it has no label for.

The live enum is inlined below rather than imported. A migration must mean the
same thing forever: importing the enum would make this revision's behaviour
change every time a later release adds or removes an event, which is exactly
the property a migration must not have.

Irreversible by nature — the downgrade cannot invent rows back. That is
acceptable here because the rows record events the product no longer has.

Revision ID: 0055
Revises: 0054
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0055"
down_revision: str | None = "0054"
branch_labels: str | None = None
depends_on: str | None = None

#: Every audit event type this revision knows about — the enum exactly as it
#: stands at revision 0055. Anything else in `audit_log` was written by a
#: version of Coffer that had an event the product has since dropped.
_LIVE_EVENT_TYPES = (
    "agent_config_file_deleted",
    "agent_config_file_written",
    "agent_mcp_entry_adopted",
    "agent_mcp_installed",
    "agent_mcp_uninstalled",
    "capability_disabled",
    "capability_enabled",
    "channel_paired",
    "channel_pairing_issued",
    "credential_deleted",
    "credential_migrated",
    "credential_read",
    "credential_set",
    "embedding_config_updated",
    "internal_engine_model_set",
    "kb_document_deleted",
    "master_key_exported",
    "master_key_imported",
    "master_key_relocated",
    "memory_cleared",
    "memory_deleted",
    "provider_internal_default_set",
    "provider_switched",
    "resource_created",
    "resource_deleted",
    "resource_disabled",
    "resource_enabled",
    "resource_scope_updated",
    "resource_updated",
    "retention_updated",
    "skill_adopted",
    "skill_bound",
    "skill_drift_remediated",
    "skill_imported",
    "skill_relinked",
    "skill_unbound",
    "skill_unmanaged_deleted",
    "skill_updated",
    "token_rotated",
)


def upgrade() -> None:
    placeholders = ", ".join(f":e{i}" for i in range(len(_LIVE_EVENT_TYPES)))
    params = {f"e{i}": value for i, value in enumerate(_LIVE_EVENT_TYPES)}
    op.get_bind().execute(
        sa.text(f"DELETE FROM audit_log WHERE event_type NOT IN ({placeholders})"),
        params,
    )


def downgrade() -> None:
    """No-op: the deleted rows record events that no longer exist."""
