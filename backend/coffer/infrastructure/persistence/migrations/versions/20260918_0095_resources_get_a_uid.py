"""every resource gets a ``uid`` — the identity its name used to pretend to be

The column added here is what replaces ``(kind, name)`` as a resource's
identity everywhere outside the database ([Resource Identity Is an Immutable
`uid`](../../../../../../docs/decisions/resource-identity-is-an-immutable-uid.md)).
The integer ``id`` is untouched and stays what it always was: the surrogate
primary key four kind-owned tables hold a foreign key to.

**Why the backfill is derived rather than random.** A uid has to mean the same
thing on every machine in the fleet, and a vault converges through a git remote
with no online handshake — so there is no moment at which two machines could
agree on a value one of them invented. What they already agree on, at the
instant they upgrade, is ``(kind, name)``: it *was* the identity until this
revision. Deriving from it with a fixed namespace makes every machine compute
the same uid for the same resource independently, and makes this migration
idempotent as a bonus — a second run recomputes the same value it wrote.

That derivation is used **here and nowhere else**. Every resource created after
this revision gets a random ``uuid4().hex`` from the application layer. If new
rows kept deriving from the name, then deleting ``foo`` and creating a fresh
``foo`` would hand the new resource the dead one's identity — its audit trail,
and on the other machine its config — which is the precise confusion this whole
change exists to end.

The unique index rather than a ``NOT NULL`` column: adding a non-null column to
``resources`` means recreating the table, and four tables hold
``FOREIGN KEY(resources.id) ON DELETE CASCADE`` against it. No revision in this
lineage has ever rebuilt this table, and doing it for a column the ORM already
declares non-null would be trading a real risk for a redundant guarantee. The
index carries the part that matters — two resources may not share a uid.

Revision ID: 0089
Revises: 0088
Create Date: 2026-09-18
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0095"
down_revision: str | None = "0094"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

#: The namespace the one-time backfill derives from. Fixed forever: change it
#: and two machines upgrading on either side of the change compute different
#: uids for the same resource, which is the one failure this design exists to
#: prevent. It is written out as a literal rather than computed from a string,
#: so no library's hashing convention can move it underneath us.
NAMESPACE = uuid.UUID("cd180388-8e6e-4bd0-a240-a8facba5ce53")

INDEX_NAME = "uq_resources_uid"


def derive_uid(kind: str, name: str) -> str:
    """The uid a pre-existing ``(kind, name)`` resolves to, on every machine."""
    return uuid.uuid5(NAMESPACE, f"{kind}:{name}").hex


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "resources" not in set(inspector.get_table_names()):
        return

    columns = {c["name"] for c in inspector.get_columns("resources")}
    if "uid" not in columns:
        op.add_column("resources", sa.Column("uid", sa.String(), nullable=True))

    rows = bind.execute(
        sa.text("SELECT id, kind, name FROM resources WHERE uid IS NULL OR uid = ''")
    ).fetchall()
    for row in rows:
        bind.execute(
            sa.text("UPDATE resources SET uid = :uid WHERE id = :id"),
            {"uid": derive_uid(row.kind, row.name), "id": row.id},
        )
    logger.info("migration.0089.uid_backfilled; rows=%s", len(rows))

    if INDEX_NAME not in {i["name"] for i in inspector.get_indexes("resources")}:
        op.create_index(INDEX_NAME, "resources", ["uid"], unique=True)


def downgrade() -> None:
    """Drop the column. Nothing else in this revision to undo.

    The uids are lost, and that is recoverable in the only sense that matters:
    stepping back below this revision puts ``(kind, name)`` back in charge, and
    stepping forward again derives exactly the same uids from exactly the same
    names. A resource created while the schema was forward — whose uid was
    random — loses its identity and is re-derived on the way up, which is the
    honest outcome and the reason the derivation is a pure function of the name.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "resources" not in set(inspector.get_table_names()):
        return
    if INDEX_NAME in {i["name"] for i in inspector.get_indexes("resources")}:
        op.drop_index(INDEX_NAME, table_name="resources")
    if "uid" in {c["name"] for c in inspector.get_columns("resources")}:
        op.drop_column("resources", "uid")
