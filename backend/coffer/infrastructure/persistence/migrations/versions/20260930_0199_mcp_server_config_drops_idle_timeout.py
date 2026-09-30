"""mcp_server configs drop ``idle_timeout_seconds``

An idle collector for upstream MCP servers was never built, so the
``idle_timeout_seconds`` field is gone from ``MCPServerConfig``, and the model
now refuses keys it does not declare. This strips the key from every stored
``mcp_server`` row, so a vault written while the field existed still loads.
Nothing else in a config is touched, and nothing reads the key back, so there
is no load-time shim.

The downgrade restores nothing: the key decided nothing, and an older build
fills in its default when it is absent.

Revision ID: 0199
Revises: 0135
Create Date: 2026-09-30
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0199"
down_revision: str | None = "0135"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The retired ``MCPServerConfig`` key, frozen at this revision.
_RETIRED_KEY = "idle_timeout_seconds"


def upgrade() -> None:
    bind = op.get_bind()
    if "resources" not in set(sa.inspect(bind).get_table_names()):
        return
    rows = bind.execute(
        sa.text("SELECT id, config_json FROM resources WHERE kind = 'mcp_server'")
    ).fetchall()
    for row_id, raw in rows:
        try:
            config = json.loads(raw)
        except (TypeError, ValueError):
            continue  # a row the app cannot read either; not this script's to fix
        if not isinstance(config, dict) or _RETIRED_KEY not in config:
            continue
        del config[_RETIRED_KEY]
        bind.execute(
            sa.text("UPDATE resources SET config_json = :cfg WHERE id = :id"),
            {"cfg": json.dumps(config), "id": row_id},
        )


def downgrade() -> None:
    """Nothing to restore: the key decided nothing, and an older build uses its
    default when it is absent."""
