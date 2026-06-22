"""slim provider connections: drop model/fast_model/wire_api, wire_format→protocol

Revision ID: 0040
Revises: 0039
Create Date: 2026-06-22

Spec 011 amendment E1/E3: a connection is a credentialed endpoint
``{protocol, base_url, credential_ref}``. The MODEL it runs leaves the
connection — it is chosen at the point of use (the per-agent binding, the
internal-engine selector, the chat surface). This migration rewrites every
``kind='provider'`` ``config_json`` row:

- rename the ``wire_format`` key to ``protocol`` (same values; ``unknown`` is a
  new member for connections whose protocol the probe could not classify),
- strip ``model`` / ``fast_model`` / ``wire_api``.

Option A (clean break): any model a user had configured on the connection is
discarded — they re-select models on the Agent page after upgrade. ``downgrade``
restores the keys with neutral placeholders (the original values are gone).

Migration scripts never import application code, so the field names stay inlined.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0040"
down_revision: str | None = "0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rows() -> list[Any]:
    bind = op.get_bind()
    return list(
        bind.execute(sa.text("SELECT id, config_json FROM resources WHERE kind = 'provider'"))
        .mappings()
        .all()
    )


def _write(row_id: object, cfg: dict[str, object]) -> None:
    op.get_bind().execute(
        sa.text("UPDATE resources SET config_json = :cfg WHERE id = :id"),
        {"cfg": json.dumps(cfg), "id": row_id},
    )


def upgrade() -> None:
    for row in _rows():
        try:
            cfg = json.loads(str(row["config_json"]))
        except (TypeError, ValueError):
            continue
        if not isinstance(cfg, dict):
            continue
        if "wire_format" in cfg:
            cfg["protocol"] = cfg.pop("wire_format")
        for dead in ("model", "fast_model", "wire_api"):
            cfg.pop(dead, None)
        _write(row["id"], cfg)


def downgrade() -> None:
    for row in _rows():
        try:
            cfg = json.loads(str(row["config_json"]))
        except (TypeError, ValueError):
            continue
        if not isinstance(cfg, dict):
            continue
        if "protocol" in cfg:
            cfg["wire_format"] = cfg.pop("protocol")
        # The original model/fast_model/wire_api are gone — restore neutral
        # placeholders so the pre-slim shape loads.
        cfg.setdefault("model", "(unknown)")
        cfg.setdefault("fast_model", None)
        cfg.setdefault("wire_api", "responses")
        _write(row["id"], cfg)
