"""an agent's fast model becomes its Haiku tier pin

The per-agent model binding carried ``fast_model``, projected into Claude
Code's deprecated ``ANTHROPIC_SMALL_FAST_MODEL`` — a key Claude Code still reads
AHEAD of the Haiku pin that replaced it. The binding now carries ``effort`` and
``tier_models`` (spec agent-registry "Carry the model binding on the agent
record"): Claude Code's background model is its Haiku tier, so a Claude Code
agent's ``fast_model`` moves into ``tier_models.haiku`` (unless a Haiku pin is
already there) and the key is stripped from every agent row. A Codex agent's
``fast_model`` never projected anything and is dropped.

``downgrade`` moves the Haiku pin back and strips ``effort`` / ``tier_models``.
Migration scripts never import application code, so the field names stay inlined.

Revision ID: 0110
Revises: 0109
Create Date: 2026-09-30
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0110"
down_revision: str | None = "0109"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rows() -> list[Any]:
    bind = op.get_bind()
    return list(
        bind.execute(sa.text("SELECT id, config_json FROM resources WHERE kind = 'agent'"))
        .mappings()
        .all()
    )


def _load(raw: object) -> dict[str, Any] | None:
    try:
        cfg = json.loads(str(raw))
    except (TypeError, ValueError):
        return None
    return cfg if isinstance(cfg, dict) else None


def _write(row_id: object, cfg: dict[str, Any]) -> None:
    op.get_bind().execute(
        sa.text("UPDATE resources SET config_json = :cfg WHERE id = :id"),
        {"cfg": json.dumps(cfg), "id": row_id},
    )


def upgrade() -> None:
    for row in _rows():
        cfg = _load(row["config_json"])
        if cfg is None or "fast_model" not in cfg:
            continue
        fast = cfg.pop("fast_model")
        if cfg.get("type") == "claude_code" and isinstance(fast, str) and fast.strip():
            tiers = cfg.get("tier_models")
            tiers = dict(tiers) if isinstance(tiers, dict) else {}
            tiers.setdefault("haiku", fast.strip())
            cfg["tier_models"] = tiers
        _write(row["id"], cfg)


def downgrade() -> None:
    for row in _rows():
        cfg = _load(row["config_json"])
        if cfg is None:
            continue
        tiers = cfg.pop("tier_models", None)
        cfg.pop("effort", None)
        haiku = tiers.get("haiku") if isinstance(tiers, dict) else None
        cfg["fast_model"] = haiku if isinstance(haiku, str) else None
        _write(row["id"], cfg)
