"""flip openai connections' wire_api from "chat" to "responses"

Revision ID: 0037
Revises: 0036
Create Date: 2026-06-22

codex-cli 0.130 dropped support for ``wire_api = "chat"`` — Codex now fails to
load ``~/.codex/config.toml`` ("`wire_api = \"chat\"` is no longer supported"),
so every chat turn errors. Existing ``openai`` provider connections (including
the rows migration 0036 created with a hard-coded ``"chat"``) carry the dead
value; flip them to ``"responses"`` so the next projection writes config Codex
accepts. ``anthropic`` ignores ``wire_api``; ``ollama`` never projects — both are
left untouched.

The on-disk ``config.toml`` is only rewritten when a connection is (re)activated;
this migration fixes the stored registry value so that re-activation projects
``responses``.

Migration scripts never import application code, so the field names stay inlined.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: str | None = "0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _remap(config_json: str, frm: str, to: str) -> str | None:
    """Return updated config JSON if this is an openai connection whose wire_api
    equals ``frm``; otherwise ``None`` (no update needed)."""
    try:
        cfg = json.loads(config_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(cfg, dict):
        return None
    if cfg.get("wire_format") != "openai" or cfg.get("wire_api") != frm:
        return None
    cfg["wire_api"] = to
    return json.dumps(cfg)


def _migrate(frm: str, to: str) -> None:
    bind = op.get_bind()
    rows = (
        bind.execute(sa.text("SELECT id, config_json FROM resources WHERE kind = 'provider'"))
        .mappings()
        .all()
    )
    for row in rows:
        updated = _remap(str(row["config_json"]), frm, to)
        if updated is not None:
            bind.execute(
                sa.text("UPDATE resources SET config_json = :cfg WHERE id = :id"),
                {"cfg": updated, "id": row["id"]},
            )


def upgrade() -> None:
    _migrate("chat", "responses")


def downgrade() -> None:
    _migrate("responses", "chat")
