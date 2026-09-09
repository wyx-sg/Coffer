"""collapse scope to an agent list and drop the sync-only tables

Revision ID: 0049
Revises: 0048
Create Date: 2026-09-09

The database half of withdrawing continuous multi-machine sync: exporting and
importing a vault bundle replaces it (ADR-016), so the machine registry, the
tombstone ledger and the sync run state have nothing left to serve, and the
machine axis of a resource's activation scope loses the machine ids that gave
it meaning (ADR-045). Two changes, one revision, because they are the same
removal.

**Scope collapses.** ``resources.scope_json`` keeps its column and its JSON-text
storage; only the shape inside changes, from a machine -> agents mapping to a
flat list of agent names:

  - ``{"<machine>": ["claude-code", "codex"]}``     -> ``["claude-code", "codex"]``
  - ``{"<m-a>": ["claude-code"], "<m-b>": ["codex"]}`` -> the union, sorted for a
    stable, reproducible result
  - any ``"*"`` value (``{"<machine>": "*"}``, ``{"*": "*"}``) -> ``null``: the
    resource was active for every agent on some machine, and with the machine
    axis gone that is simply "every agent"
  - ``{}``                                           -> ``[]`` (dormant, preserved)
  - ``null``                                         -> ``null`` (untouched)

Only ``mcp_server`` and ``skill`` still declare a scope. ``agent`` and
``channel`` no longer do — an agent scoping itself is meaningless, and a channel
now simply runs where it is enabled — so their stored value is CLEARED to
``null`` rather than collapsed. That deliberately voids 0047's
``config_json.runs_on -> scope_json`` backfill: its ``{}`` ("bound to no
machine") would otherwise survive as ``[]`` and silence every channel. Clearing
also keeps a stale mapping from reaching ``agent_in_scope``, which now tests
membership in a list and would quietly match a dict's keys instead.

**Tables dropped.** ``sync_config``, ``sync_state`` (0019), ``machine_identity``
(0042) and ``sync_tombstones`` (0043). Each drop is guarded by an existence
check, so a database missing one — an old install, a partial earlier run — still
upgrades. Their rows were machine-local runtime state, never vault data, so
nothing exportable is lost.

``downgrade`` recreates the four tables EMPTY (mirroring 0030's treatment of the
per-agent MCP scope tables) so the chain stays runnable downwards: 0019's
downgrade drops ``sync_state``/``sync_config`` unguarded, and 0043/0044/0045
expect their columns to exist. The scope collapse is not reversed — a machine id
cannot be invented back out of an agent list — which is stated here rather than
faked with a placeholder key.

Idempotent: a re-run finds lists (left alone), nulls, and no tables to drop.
Migration scripts never import application code, so the kind names and the
wildcard stay inlined and frozen against later model changes.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0049"
down_revision: str | None = "0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Kinds that still declare an activation scope (ADR-045). Every other kind's
# stored scope is cleared. Inlined: migrations never import application code.
_SCOPED_KINDS = ("mcp_server", "skill")
_WILDCARD = "*"

# Dropped in reverse creation order; none of them is referenced by a foreign key.
_DROPPED_TABLES = ("sync_tombstones", "machine_identity", "sync_state", "sync_config")


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def _collapsed(kind: str, raw: str) -> str | None:
    """Return the post-collapse ``scope_json`` text for one row.

    ``None`` means SQL NULL — active for every agent. Anything unparseable or
    unrecognised also collapses to NULL: the pre-scope default is the only safe
    reading of a value no code can interpret any more.
    """
    if kind not in _SCOPED_KINDS:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if isinstance(value, list):
        return raw  # already collapsed (a re-run, or a value written post-0049)
    if not isinstance(value, dict):
        return None
    agents: set[str] = set()
    for entry in value.values():
        if entry == _WILDCARD:
            return None  # every agent on that machine -> every agent
        if isinstance(entry, list):
            agents.update(a for a in entry if isinstance(a, str) and a)
    return json.dumps(sorted(agents))


def upgrade() -> None:
    bind = op.get_bind()
    rows = (
        bind.execute(
            sa.text("SELECT id, kind, scope_json FROM resources WHERE scope_json IS NOT NULL")
        )
        .mappings()
        .all()
    )
    for row in rows:
        collapsed = _collapsed(row["kind"], row["scope_json"])
        if collapsed == row["scope_json"]:
            continue
        bind.execute(
            sa.text("UPDATE resources SET scope_json = :scope WHERE id = :id"),
            {"scope": collapsed, "id": row["id"]},
        )

    # SQLite drops a table's indexes with the table, so no explicit drop_index.
    for table in _DROPPED_TABLES:
        if _has_table(table):
            op.drop_table(table)


def downgrade() -> None:
    # Recreate the tables exactly as 0019/0042/0043 did, plus the columns
    # 0043/0044/0045 added, so those revisions' own downgrades find what they
    # expect. They come back EMPTY: their contents were machine-local runtime
    # state that the upgrade legitimately discarded.
    if not _has_table("sync_config"):
        op.create_table(
            "sync_config",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("remote", sa.String(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("auto", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="300"),
            sa.Column("branch", sa.String(), nullable=False, server_default="main"),
            sa.Column("updated_at", sa.String(), nullable=False),
            sa.Column(
                "poll_remote_seconds", sa.Integer(), nullable=False, server_default="15"
            ),  # 0044
        )
    if not _has_table("sync_state"):
        op.create_table(
            "sync_state",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("status", sa.String(), nullable=False, server_default="unconfigured"),
            sa.Column("last_sync_at", sa.String(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("conflict_paths_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("locked_refs_json", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("updated_at", sa.String(), nullable=False),
            sa.Column(
                "quarantined_refs_json", sa.Text(), nullable=False, server_default="[]"
            ),  # 0043
            sa.Column("failed_state_json", sa.Text(), nullable=False, server_default="[]"),  # 0045
        )
    op.execute(
        "CREATE TABLE IF NOT EXISTS machine_identity ("
        "id INTEGER NOT NULL, "
        "machine_id VARCHAR NOT NULL, "
        "display_name VARCHAR NOT NULL, "
        "created_at VARCHAR NOT NULL, "
        "updated_at VARCHAR NOT NULL, "
        "CONSTRAINT pk_machine_identity PRIMARY KEY (id), "
        "CONSTRAINT ck_machine_identity_singleton CHECK (id = 1), "
        "CONSTRAINT uq_machine_identity_machine_id UNIQUE (machine_id)"
        ")"
    )
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
    # The scope collapse is deliberately NOT reversed: the machine ids it folded
    # away came from a registry this same removal deleted, so there is nothing
    # to restore them from. A downgraded database keeps agent-list scopes, which
    # the pre-0049 reader treats as unscoped rather than misreading them.
