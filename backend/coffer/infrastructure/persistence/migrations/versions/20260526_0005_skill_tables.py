"""skill kind tables (spec 005-skill-manager)

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-26

Adds the skill_agent_bindings join table that the skill manager owns, and
migrates the agent kind's persisted config JSON from the legacy ``skill_dir``
override to ``config_dir`` (skills are now delivered to ``<config_dir>/skills``).
The rewrite preserves a custom override instead of silently reverting skill
delivery to the type default. Chains after 0004 (audit index).
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _derive_config_dir(skill_dir: str) -> str:
    """Map a legacy ``skill_dir`` override onto a ``config_dir``.

    Skills used to be delivered to ``skill_dir`` directly; now they go to
    ``<config_dir>/skills``. A ``<dir>/skills`` override therefore maps to
    ``config_dir=<dir>`` (same on-disk location); any other custom dir
    becomes the config dir itself (skills land in its ``skills/`` subfolder).
    """
    p = pathlib.PurePath(skill_dir)
    return str(p.parent) if p.name == "skills" else skill_dir


def _migrate_agent_config_dir() -> None:
    """Rewrite agent rows: drop ``skill_dir``, set ``config_dir`` from it."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, config_json FROM resources WHERE kind = 'agent'")
    ).fetchall()
    for rid, raw in rows:
        try:
            cfg = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            continue
        if not isinstance(cfg, dict) or "skill_dir" not in cfg:
            continue
        legacy = cfg.pop("skill_dir")
        if legacy and not cfg.get("config_dir"):
            cfg["config_dir"] = _derive_config_dir(legacy)
        bind.execute(
            sa.text("UPDATE resources SET config_json = :c WHERE id = :i"),
            {"c": json.dumps(cfg), "i": rid},
        )


def upgrade() -> None:
    op.create_table(
        "skill_agent_bindings",
        sa.Column(
            "skill_resource_id",
            sa.Integer(),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_resource_id",
            sa.Integer(),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_linked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_link_path", sa.Text(), nullable=True),
        sa.Column("link_mode", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint(
            "skill_resource_id",
            "agent_resource_id",
            name="pk_skill_agent_bindings",
        ),
    )
    op.create_index(
        "idx_bindings_agent",
        "skill_agent_bindings",
        ["agent_resource_id", "enabled"],
    )
    op.create_index(
        "idx_bindings_skill",
        "skill_agent_bindings",
        ["skill_resource_id", "enabled"],
    )
    _migrate_agent_config_dir()


def downgrade() -> None:
    op.drop_index("idx_bindings_skill", table_name="skill_agent_bindings")
    op.drop_index("idx_bindings_agent", table_name="skill_agent_bindings")
    op.drop_table("skill_agent_bindings")
