"""sync tombstone ledger + quarantined refs (spec 010 amendment, ADR-043)

Revision ID: 0043
Revises: 0042
Create Date: 2026-07-10

Deletion of a config resource is recorded in a local ledger and exported as an
explicit workspace tombstone; import stops inferring deletions from absence.
``sync_state`` additionally tracks the refs whose import failed on this machine
(quarantine) so they are retried and surfaced instead of silently dropped.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0043"
down_revision: str | None = "0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent (IF NOT EXISTS) so a partial/interrupted migration self-heals.
    op.execute(
        "CREATE TABLE IF NOT EXISTS sync_tombstones ("
        "id INTEGER NOT NULL, "
        "kind VARCHAR NOT NULL, "
        "name VARCHAR NOT NULL, "
        "deleted_at VARCHAR NOT NULL, "
        "CONSTRAINT pk_sync_tombstones PRIMARY KEY (id), "
        "CONSTRAINT uq_sync_tombstones_kind_name UNIQUE (kind, name)"
        ")"
    )
    # SQLite has no IF NOT EXISTS for columns; probe first so re-running heals.
    cols = [
        row[1] for row in op.get_bind().exec_driver_sql("PRAGMA table_info(sync_state)").fetchall()
    ]
    if "quarantined_refs_json" not in cols:
        op.execute(
            "ALTER TABLE sync_state ADD COLUMN quarantined_refs_json TEXT NOT NULL DEFAULT '[]'"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sync_tombstones")
    cols = [
        row[1] for row in op.get_bind().exec_driver_sql("PRAGMA table_info(sync_state)").fetchall()
    ]
    if "quarantined_refs_json" in cols:
        op.execute("ALTER TABLE sync_state DROP COLUMN quarantined_refs_json")
