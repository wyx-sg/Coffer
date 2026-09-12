"""the global embedding config NAMES a connection instead of restating one

``embedding_config`` used to carry its own ``provider`` (an embedding-protocol
id), ``base_url`` and ``credential_ref`` — a second, parallel place to type an
endpoint and a key that the Connections page already holds. It now carries
``connection``: the NAME of a ``provider`` resource, plus the model id, exactly
the "pick a provider, then pick a model" shape the internal-engine setting has
(spec knowledge FR-077). The wire, base URL and credential are read from that
connection at use time.

Mapping the existing row: the connection it MEANT is the one pointing at the
same place, so this matches on ``base_url`` first (normalised for a trailing
slash) and falls back to ``credential_ref`` — two configs sharing one vault
entry are the same endpoint in practice. When nothing matches, the row keeps
its dimensions and chunk defaults but is left with NO connection and
``enabled = 0``: inventing a connection would put a half-real endpoint on the
Connections page, whereas a disabled config is a state the app already handles —
retrieval degrades to keyword/grep exactly as on an install that never
configured embedding, and the user picks a connection when they next look.

The three old columns are dropped in the same revision: the data is corrected
here, so no load-time shim reads them afterwards.

Idempotent: a database that already has ``connection`` is skipped, so a re-run
matches nothing. Column and table names are inlined rather than imported — a
migration must mean the same thing forever.

Revision ID: 0065
Revises: 0064
Create Date: 2026-09-12
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0065"
down_revision: str | None = "0064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "embedding_config"


def _columns() -> set[str]:
    bind = op.get_bind()
    return {row[1] for row in bind.execute(sa.text(f"PRAGMA table_info({_TABLE})")).fetchall()}


def _norm(url: str | None) -> str:
    return (url or "").strip().rstrip("/").lower()


def _matching_connection(base_url: str | None, credential_ref: str | None) -> str | None:
    """The provider resource the old settings were pointing at, if any."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT name, config_json FROM resources WHERE kind = 'provider'")
    ).fetchall()
    by_ref: str | None = None
    for name, raw in rows:
        try:
            config = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(config, dict):
            continue
        if base_url and _norm(config.get("base_url")) == _norm(base_url):
            return str(name)
        if credential_ref and config.get("credential_ref") == credential_ref:
            by_ref = by_ref or str(name)
    return by_ref


def upgrade() -> None:
    columns = _columns()
    if not columns or "connection" in columns:
        return  # no table on this database, or already migrated
    bind = op.get_bind()
    row = bind.execute(
        sa.text(f"SELECT base_url, credential_ref FROM {_TABLE} WHERE id = 1")
    ).fetchone()
    connection = _matching_connection(row[0], row[1]) if row is not None else None

    with op.batch_alter_table(_TABLE) as batch:
        batch.add_column(sa.Column("connection", sa.String(), nullable=True))
    if row is not None:
        bind.execute(
            sa.text(f"UPDATE {_TABLE} SET connection = :conn, enabled = :enabled WHERE id = 1"),
            {"conn": connection, "enabled": 1 if connection else 0},
        )
    with op.batch_alter_table(_TABLE) as batch:
        for dead in ("provider", "base_url", "credential_ref"):
            if dead in columns:
                batch.drop_column(dead)


def downgrade() -> None:
    """Put the three restated columns back, empty. Which protocol/base URL/key
    the config used to spell out is not recoverable from a connection NAME
    without resolving that connection, and nothing below this revision would
    read the name anyway — so the row comes back unconfigured."""
    columns = _columns()
    if not columns or "connection" not in columns:
        return
    with op.batch_alter_table(_TABLE) as batch:
        for revived in ("provider", "base_url", "credential_ref"):
            if revived not in columns:
                batch.add_column(sa.Column(revived, sa.String(), nullable=True))
        batch.drop_column("connection")
    op.get_bind().execute(sa.text(f"UPDATE {_TABLE} SET enabled = 0 WHERE id = 1"))
