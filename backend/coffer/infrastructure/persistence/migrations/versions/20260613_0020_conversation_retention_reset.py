"""reset legacy single-stage conversation retention to the two-stage model

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-13

Spec 008's conversation retention became a two-stage lifecycle: auto-archive
idle threads (``conversations_archive``, matched by ``updated_at``) then delete
archived threads (``conversations``, matched by ``archived_at``). With that, the
``conversations`` retention row's meaning flipped from "delete by updated_at" to
"delete by archived_at".

But retention rows are seeded idempotently at startup (``initialize_defaults``
only fills MISSING rows), so a pre-existing single-stage install's
``conversations`` row keeps its old numeric value while being silently
reinterpreted against ``archived_at`` — and the new archive stage is never
configured. This migration repairs such legacy installs, identified by a
``conversations`` retention row WITHOUT the new ``conversations_archive`` row:
it resets the delete stage to the new default and seeds the archive stage,
while honouring a disabled (NULL) retention choice (kept disabled — never
silently re-enabled). Installs already on the two-stage model (both rows
present) are left untouched, so a deliberately-customised value is not clobbered.

Retention rows live in ``retention_policies`` (seeded at runtime, not by an
earlier migration), so on a fresh ``upgrade head`` there is no
``conversations`` row and this migration is a no-op.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# New two-stage defaults — mirror build_prunable_registry in
# coffer/surfaces/http/app_mcp_composition.py (migrations never import app code).
_ARCHIVE_DEFAULT_DAYS = 7
_DELETE_DEFAULT_DAYS = 30


def upgrade() -> None:
    bind = op.get_bind()
    if "retention_policies" not in inspect(bind).get_table_names():
        return  # mid-chain on a fresh DB; nothing seeded yet
    conv = bind.execute(
        sa.text("SELECT retention_days FROM retention_policies WHERE table_name = 'conversations'")
    ).fetchone()
    if conv is None:
        return  # no conversation retention configured yet (rows seed at runtime)
    already_two_stage = bind.execute(
        sa.text("SELECT 1 FROM retention_policies WHERE table_name = 'conversations_archive'")
    ).fetchone()
    if already_two_stage is not None:
        return  # already migrated — leave any customised values untouched

    # Legacy single-stage install. Honour a disabled (NULL) choice; otherwise
    # reset to the new two-stage defaults.
    disabled = conv[0] is None
    archive_days = None if disabled else _ARCHIVE_DEFAULT_DAYS
    delete_days = None if disabled else _DELETE_DEFAULT_DAYS
    now = datetime.now(tz=UTC).isoformat()

    # Reset the delete stage: its clock is now archived_at (not updated_at), so
    # the old value no longer applies and its prune bookkeeping is stale.
    bind.execute(
        sa.text(
            "UPDATE retention_policies SET retention_days = :days, last_pruned_at = NULL, "
            "last_pruned_rows = 0, updated_at = :now WHERE table_name = 'conversations'"
        ),
        {"days": delete_days, "now": now},
    )
    # Seed the new archive stage.
    bind.execute(
        sa.text(
            "INSERT INTO retention_policies "
            "(table_name, retention_days, last_pruned_at, last_pruned_rows, updated_at) "
            "VALUES ('conversations_archive', :days, NULL, 0, :now)"
        ),
        {"days": archive_days, "now": now},
    )


def downgrade() -> None:
    # Forward-only data repair. Collapsing back to single-stage just drops the
    # archive row so the chain stays reversible; the old reinterpreted value
    # cannot be meaningfully reconstructed, and pre-0020 code simply re-seeds
    # whatever it needs at startup.
    bind = op.get_bind()
    if "retention_policies" not in inspect(bind).get_table_names():
        return
    bind.execute(
        sa.text("DELETE FROM retention_policies WHERE table_name = 'conversations_archive'")
    )
