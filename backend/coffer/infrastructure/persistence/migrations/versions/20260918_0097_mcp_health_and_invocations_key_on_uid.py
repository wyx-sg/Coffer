"""the two MCP tables that keyed rows by a server's NAME start keying them by its uid

``mcp_server_health.resource_name`` (its PRIMARY KEY) and
``mcp_invocations.resource_name`` (plus ``idx_invocations_resource``) were the
last two places in the MCP kind that pointed at a server by the label its owner
is allowed to change ([Resource Identity Is an Immutable
`uid`](../../../../../../docs/decisions/resource-identity-is-an-immutable-uid.md)).
Neither is a foreign key, so nothing enforced the pointer, and both broke
quietly the moment a rename became possible for every kind:

* **health** is one row per server. Renaming the server orphaned its row — a
  primary key nothing would ever write to again — and the status surface went
  blank for a server that had tested green a second earlier, because the lookup
  now asked about a key that had never been written.
* **invocations** is history. A rename split one server's past in two at the
  moment of the edit, and — worse, because it is silent — a later registration
  reusing the freed name inherited the dead server's record as if it were its
  own.

By this revision 0089 has minted a ``uid`` for every resource and 0090 has
rewritten the cross-references that hold one, so every row in ``resources`` has
a uid to point at and the rewrite below is a pure lookup.

## The rows whose name resolves to nothing

Both tables can hold a name that matches no ``mcp_server`` row: a server the
user deleted, or one that was renamed before this revision ran. There is no uid
to be found for those, and inventing one is not an option — so each table is
told explicitly what to do, and the two answers differ because the tables mean
different things.

**Health rows are DROPPED.** A health row is a cache of the last "test
connection", derived entirely from an action the user can repeat, and it is
already machine-local and already excluded from the vault. A row about a server
that no longer exists answers a question nobody can ask: no surface looks it up,
because every surface starts from a registered server. Keeping it would mean
carrying a permanent unreachable key in a table whose whole shape is one row per
server. Nothing is widened by the drop — health is not an allow-list, and the
only consequence of losing a row is that the next "test connection" writes it
again.

**Invocation rows are KEPT, under ``deleted:<name>``.** The invocation log is
history, and history is the one thing a migration must not quietly edit: these
rows are the record of what an agent actually did, they feed retention, and the
user can still read them on the activity page. Their identity was never
recorded and cannot be recovered, so what survives is the label they did carry,
behind a marker that is visibly not a uid (a name may not contain ``:``, so the
marker cannot collide with one, and a uid is 32 hex characters, so it cannot
either). The row then joins to no resource — which is the truth about it — and
the tiering query's inner join skips it, correctly, since a deleted server's
tools are not in any catalogue to be ranked.

## The rows that read exactly ``coffer``

Coffer's own ``coffer__*`` built-in tools write their invocations into the same
log under the sentinel ``"coffer"``; there is no ``mcp_server`` row behind them
and so no uid to record. Those rows are left exactly as they are, and this
revision refuses to resolve that value even if a registered server happens to be
*called* ``coffer`` — attributing Coffer's own built-in calls to one of the
user's servers would be a fabrication. The flip side is honest and worth
stating: if such a server exists, its own rows are indistinguishable from the
built-ins' and stay pooled with them. That conflation is not introduced here —
a name-keyed log never told the two apart — and it ends for every row written
after this revision, which carries a real uid.

Revision ID: 0091
Revises: 0090
Create Date: 2026-09-18
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0097"
down_revision: str | None = "0096"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

#: The sentinel Coffer's own built-in tools log under; see the module docstring.
#: Mirrors ``domain.mcp.capability.BUILTIN_SERVER_UID``, spelled out rather than
#: imported because a migration must keep meaning what it meant on the day it
#: ran, whatever the application layer renames later.
_BUILTIN = "coffer"

#: The marker an invocation carries when its server was already gone; mirrors
#: ``domain.mcp.capability.DELETED_SERVER_UID_PREFIX`` for the same reason.
_DELETED_PREFIX = "deleted:"

_INVOCATION_INDEX = "idx_invocations_resource"


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _indexes(table: str) -> set[str]:
    # ``str(...)`` because the reflected name is typed optional; an index with
    # no name cannot exist in this schema, and coercing keeps the set homogeneous.
    return {str(i["name"]) for i in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    tables = _tables()
    if "resources" not in tables:
        return
    if "mcp_server_health" in tables:
        _health_to_uid()
    if "mcp_invocations" in tables:
        _invocations_to_uid()


def _health_to_uid() -> None:
    """Rebuild ``mcp_server_health`` keyed on the uid, dropping unresolvable rows.

    A rebuild rather than a ``RENAME COLUMN`` + ``UPDATE``, because the column is
    the PRIMARY KEY: rewriting a unique column in place asks SQLite to hold
    uniqueness true at every intermediate row, and an ``INSERT … SELECT`` with
    the join in it simply never reaches an intermediate state. The join is an
    INNER one, which is where "unresolvable rows are dropped" is actually
    expressed — deliberately, and argued in this revision's docstring.

    Idempotent by the column check: a second run finds ``resource_uid`` already
    there and does nothing.
    """
    if "resource_uid" in _columns("mcp_server_health"):
        return
    bind = op.get_bind()
    before = bind.execute(sa.text("SELECT count(*) FROM mcp_server_health")).scalar_one()
    bind.execute(
        sa.text(
            "CREATE TABLE mcp_server_health_uid ("
            " resource_uid VARCHAR NOT NULL,"
            " status VARCHAR NOT NULL,"
            " checked_at TIMESTAMP NOT NULL,"
            " PRIMARY KEY (resource_uid))"
        )
    )
    bind.execute(
        sa.text(
            "INSERT INTO mcp_server_health_uid (resource_uid, status, checked_at) "
            "SELECT r.uid, h.status, h.checked_at FROM mcp_server_health h "
            "JOIN resources r ON r.kind = 'mcp_server' AND r.name = h.resource_name"
        )
    )
    after = bind.execute(sa.text("SELECT count(*) FROM mcp_server_health_uid")).scalar_one()
    bind.execute(sa.text("DROP TABLE mcp_server_health"))
    bind.execute(sa.text("ALTER TABLE mcp_server_health_uid RENAME TO mcp_server_health"))
    logger.info("migration.0091.health_rekeyed; kept=%s dropped=%s", after, before - after)


def _invocations_to_uid() -> None:
    """Re-key ``mcp_invocations`` in place, keeping every row.

    In place — ``RENAME COLUMN`` plus two ``UPDATE``s — because this table is the
    largest in the vault and nothing about it is unique, so there is no
    intermediate state to protect and no reason to copy the whole log.

    The two updates run in this order on purpose. Marking the unresolvable rows
    FIRST puts them beyond the reach of the second update (``deleted:`` contains
    a colon, which the framework's name rule forbids, so such a value can never
    match a resource's name), which makes the pair safe to run in either
    sequence of partial failures and safe to run twice.
    """
    bind = op.get_bind()
    if "resource_uid" not in _columns("mcp_invocations"):
        # The index names the column, so drop it before the rename and rebuild
        # it after — rather than trusting SQLite's own index rewriting, which
        # depends on the connection's ``legacy_alter_table`` setting.
        if _INVOCATION_INDEX in _indexes("mcp_invocations"):
            op.drop_index(_INVOCATION_INDEX, table_name="mcp_invocations")
        bind.execute(
            sa.text("ALTER TABLE mcp_invocations RENAME COLUMN resource_name TO resource_uid")
        )

    orphaned = bind.execute(
        sa.text(
            "UPDATE mcp_invocations SET resource_uid = :prefix || resource_uid "
            "WHERE resource_uid <> :builtin "
            "  AND resource_uid NOT LIKE :prefix_glob "
            "  AND resource_uid NOT IN (SELECT uid FROM resources WHERE kind = 'mcp_server') "
            "  AND NOT EXISTS ("
            "    SELECT 1 FROM resources r"
            "     WHERE r.kind = 'mcp_server' AND r.name = mcp_invocations.resource_uid)"
        ),
        {"prefix": _DELETED_PREFIX, "builtin": _BUILTIN, "prefix_glob": f"{_DELETED_PREFIX}%"},
    ).rowcount

    resolved = bind.execute(
        sa.text(
            "UPDATE mcp_invocations SET resource_uid = ("
            "  SELECT r.uid FROM resources r"
            "   WHERE r.kind = 'mcp_server' AND r.name = mcp_invocations.resource_uid) "
            "WHERE resource_uid <> :builtin "
            "  AND EXISTS ("
            "    SELECT 1 FROM resources r"
            "     WHERE r.kind = 'mcp_server' AND r.name = mcp_invocations.resource_uid)"
        ),
        {"builtin": _BUILTIN},
    ).rowcount

    if _INVOCATION_INDEX not in _indexes("mcp_invocations"):
        op.create_index(
            _INVOCATION_INDEX,
            "mcp_invocations",
            ["resource_uid", sa.text("timestamp DESC")],
        )
    logger.info("migration.0091.invocations_rekeyed; resolved=%s orphaned=%s", resolved, orphaned)


def downgrade() -> None:
    """Put the names back where a name can still be found, and say so where it cannot.

    The invocation log survives intact: a uid that still matches a server
    resolves to that server's CURRENT name, and a ``deleted:<name>`` row gives
    back the name it was carrying all along. What a downgrade cannot recover is a
    row whose server was registered *and* deleted while the schema was forward —
    its uid resolves to nothing and there is no name anywhere to look up — so the
    uid string itself is left in the column. That is not a name and does not
    pretend to be one; it is the only honest value available, and the alternative
    (blanking it, or deleting the row) would destroy history to make a column
    look tidier.

    Health goes the other way and loses rows again: a uid that no longer matches
    a server has no name, and the pre-0091 schema made that column the primary
    key, so there is nothing to put there. The rows are dropped, which costs
    exactly one "test connection" to rebuild — the same trade this revision's
    upgrade makes, in the same direction, for the same reason.
    """
    tables = _tables()
    if "resources" not in tables:
        return
    bind = op.get_bind()

    if "mcp_invocations" in tables and "resource_uid" in _columns("mcp_invocations"):
        if _INVOCATION_INDEX in _indexes("mcp_invocations"):
            op.drop_index(_INVOCATION_INDEX, table_name="mcp_invocations")
        bind.execute(
            sa.text("ALTER TABLE mcp_invocations RENAME COLUMN resource_uid TO resource_name")
        )
        bind.execute(
            sa.text(
                "UPDATE mcp_invocations SET resource_name = ("
                "  SELECT r.name FROM resources r"
                "   WHERE r.kind = 'mcp_server' AND r.uid = mcp_invocations.resource_name) "
                "WHERE EXISTS ("
                "  SELECT 1 FROM resources r"
                "   WHERE r.kind = 'mcp_server' AND r.uid = mcp_invocations.resource_name)"
            )
        )
        bind.execute(
            sa.text(
                "UPDATE mcp_invocations "
                "SET resource_name = substr(resource_name, :cut) "
                "WHERE resource_name LIKE :prefix_glob"
            ),
            {"cut": len(_DELETED_PREFIX) + 1, "prefix_glob": f"{_DELETED_PREFIX}%"},
        )
        op.create_index(
            _INVOCATION_INDEX,
            "mcp_invocations",
            ["resource_name", sa.text("timestamp DESC")],
        )

    if "mcp_server_health" in tables and "resource_uid" in _columns("mcp_server_health"):
        bind.execute(
            sa.text(
                "CREATE TABLE mcp_server_health_named ("
                " resource_name VARCHAR NOT NULL,"
                " status VARCHAR NOT NULL,"
                " checked_at TIMESTAMP NOT NULL,"
                " PRIMARY KEY (resource_name))"
            )
        )
        bind.execute(
            sa.text(
                "INSERT INTO mcp_server_health_named (resource_name, status, checked_at) "
                "SELECT r.name, h.status, h.checked_at FROM mcp_server_health h "
                "JOIN resources r ON r.kind = 'mcp_server' AND r.uid = h.resource_uid"
            )
        )
        bind.execute(sa.text("DROP TABLE mcp_server_health"))
        bind.execute(sa.text("ALTER TABLE mcp_server_health_named RENAME TO mcp_server_health"))
