"""add resources.scope_json (framework-level machine x agent scope, ADR-045)

Revision ID: 0046
Revises: 0045
Create Date: 2026-07-10

Every Resource gains an optional machine x agent activation scope: which
machines (and, for some kinds, which agents on those machines) a resource is
visible to. NULL means unscoped (visible everywhere) — the pre-scope default,
so every existing row is unaffected. Additive column on the kind-agnostic
`resources` table (mirrors the `documents.locked` guarded-ADD-COLUMN
convention from 0025).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "0046"
down_revision: str | None = "0045"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    return any(c["name"] == column for c in inspect(bind).get_columns(table))


def upgrade() -> None:
    if not _has_column("resources", "scope_json"):
        op.execute("ALTER TABLE resources ADD COLUMN scope_json TEXT")


def downgrade() -> None:
    if _has_column("resources", "scope_json"):
        op.drop_column("resources", "scope_json")
