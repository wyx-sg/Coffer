"""Secrets go to a new destination only with a present human's approval.

Three tables for the secret boundary (ADR
only-a-present-human-sees-a-secret-or-sends-it-somewhere-new, spec credentials
"Hold a secret for a new destination until a person approves it"):

* ``secret_bindings`` — each secret approved for one slot of one destination,
  pinned to the fingerprint of the target that receives the value;
* ``secret_approvals`` — the changes waiting for the desktop app, a pending
  value replacement held as ciphertext;
* ``secret_boundary_settings`` — the ``require_approval`` switch and the
  one-time marker that the bindings in use before this revision were adopted.

Nothing is back-filled here: the daemon adopts every binding that is already in
use at its first start on this revision, through the same code that computes a
binding's target at the moment of use, so the adopted fingerprint cannot drift
from the one checked later.

Revision ID: 0112
Revises: 0111
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0112"
down_revision: str | None = "0111"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "secret_bindings",
        sa.Column("ref", sa.String(), primary_key=True),
        sa.Column("destination_kind", sa.String(), primary_key=True),
        sa.Column("destination_uid", sa.String(), primary_key=True),
        sa.Column("slot", sa.String(), primary_key=True),
        sa.Column("target_fingerprint", sa.String(), nullable=False),
        sa.Column("approved_at", sa.String(), nullable=False),
        sa.Column("approval_id", sa.String(), nullable=True),
    )
    op.create_table(
        "secret_approvals",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("op", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("requested_by", sa.String(), nullable=False),
        sa.Column("ref", sa.String(), nullable=True),
        sa.Column("destination_kind", sa.String(), nullable=True),
        sa.Column("destination_uid", sa.String(), nullable=True),
        sa.Column("destination_label", sa.String(), nullable=True),
        sa.Column("slot", sa.String(), nullable=True),
        sa.Column("target", sa.Text(), nullable=True),
        sa.Column("target_fingerprint", sa.String(), nullable=True),
        sa.Column("pending_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("decided_at", sa.String(), nullable=True),
        sa.Column("decided_by", sa.String(), nullable=True),
    )
    op.create_index("idx_secret_approvals_status", "secret_approvals", ["status"])
    op.create_table(
        "secret_boundary_settings",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.String(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("secret_boundary_settings")
    op.drop_index("idx_secret_approvals_status", table_name="secret_approvals")
    op.drop_table("secret_approvals")
    op.drop_table("secret_bindings")
