"""The secret store says "secret", and each secret records when it was last used.

Two changes in one revision.

**Last used.** The Secrets page lists each secret with when it was last used
(spec secret "List every stored and cited secret with what uses it"). The store
stamps ``last_used_at`` when it decrypts a value for a consumer; the column is
machine-local — sync carries only ref and ciphertext — and nullable, because a
secret stored before this revision has never been seen in use. Nothing to
back-fill: no earlier record says when a value was used.

**One word.** Coffer's word for a value it stores is *secret*; the internals
still said *credential*. Every stored name that said so is rewritten, with no
alias left behind and no reader that accepts the old name:

- the table ``credentials`` becomes ``secrets``;
- ``sync_remotes.credential_ref`` becomes ``secret_ref`` and
  ``sync_remotes.include_credentials`` becomes ``include_secrets``;
- the audit event types ``credential_set``, ``credential_read``,
  ``credential_deleted``, ``credential_migrated`` and ``credential_revealed``
  become ``secret_set``, ``secret_read``, ``secret_deleted``,
  ``secret_migrated`` and ``secret_revealed`` in every ``audit_log`` row;
- in each resource's ``config_json``, an ``mcp_server``'s
  ``transport.credential_refs`` becomes ``transport.secret_refs`` and a
  ``provider``'s ``credential_ref`` becomes ``secret_ref``. Nothing else in a
  config is touched, and a row whose config is not a JSON object, or that
  already carries the new key, is left exactly as found.

An audit row's ``details`` is a record of what was written at the time and is
not rewritten. Ref strings carry no "credential" and are unchanged, so every
ciphertext stays at its address.

The downgrade reverses each rename.

Revision ID: 0134
Revises: 0116
Create Date: 2026-09-30
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0134"
down_revision: str | None = "0116"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Old audit event type -> new.
EVENT_TYPES: dict[str, str] = {
    "credential_set": "secret_set",
    "credential_read": "secret_read",
    "credential_deleted": "secret_deleted",
    "credential_migrated": "secret_migrated",
    "credential_revealed": "secret_revealed",
}

#: Old ``sync_remotes`` column -> new.
SYNC_REMOTE_COLUMNS: dict[str, str] = {
    "credential_ref": "secret_ref",
    "include_credentials": "include_secrets",
}


def _rename_columns(mapping: dict[str, str]) -> None:
    """SQLite's own ``RENAME COLUMN``: a batch rebuild would not carry the
    table's CHECK constraints across (SQLite does not reflect them)."""
    for old, new in mapping.items():
        op.execute(f"ALTER TABLE sync_remotes RENAME COLUMN {old} TO {new}")


def _rename_key(obj: dict[str, Any], old: str, new: str) -> bool:
    """Move ``obj[old]`` to ``obj[new]`` unless ``new`` is already there."""
    if old not in obj or new in obj:
        return False
    obj[new] = obj.pop(old)
    return True


def rewrite_config(kind: str, config: Any, *, forward: bool) -> bool:
    """Rename the secret-ref key of one resource config in place.

    Returns whether anything changed. Only the two kinds whose config cites a
    secret under a "credential" key are touched."""
    if not isinstance(config, dict):
        return False
    if kind == "mcp_server":
        transport = config.get("transport")
        if not isinstance(transport, dict):
            return False
        old, new = ("credential_refs", "secret_refs")
        return _rename_key(transport, *((old, new) if forward else (new, old)))
    if kind == "provider":
        old, new = ("credential_ref", "secret_ref")
        return _rename_key(config, *((old, new) if forward else (new, old)))
    return False


def _rewrite_configs(*, forward: bool) -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, kind, config_json FROM resources WHERE kind IN ('mcp_server', 'provider')"
        )
    ).fetchall()
    for row_id, kind, raw in rows:
        try:
            config = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if rewrite_config(kind, config, forward=forward):
            conn.execute(
                sa.text("UPDATE resources SET config_json = :c WHERE id = :id"),
                {"c": json.dumps(config), "id": row_id},
            )


def _rewrite_event_types(mapping: dict[str, str]) -> None:
    conn = op.get_bind()
    for old, new in mapping.items():
        conn.execute(
            sa.text("UPDATE audit_log SET event_type = :new WHERE event_type = :old"),
            {"new": new, "old": old},
        )


def upgrade() -> None:
    with op.batch_alter_table("credentials") as batch:
        batch.add_column(sa.Column("last_used_at", sa.String(), nullable=True))
    op.rename_table("credentials", "secrets")
    _rename_columns(SYNC_REMOTE_COLUMNS)
    _rewrite_event_types(EVENT_TYPES)
    _rewrite_configs(forward=True)


def downgrade() -> None:
    _rewrite_configs(forward=False)
    _rewrite_event_types({new: old for old, new in EVENT_TYPES.items()})
    _rename_columns({new: old for old, new in SYNC_REMOTE_COLUMNS.items()})
    op.rename_table("secrets", "credentials")
    with op.batch_alter_table("credentials") as batch:
        batch.drop_column("last_used_at")
