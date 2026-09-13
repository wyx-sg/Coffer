"""drop the audit rows for a setting that no longer writes any

``daemon_port_set`` leaves ``AuditEventType`` with the route that was its only
writer: the daemon's port stops being reachable over HTTP and is set from the
CLI alone (spec mcp-gateway FR-028). The CLI cannot take the event over,
either — it has to work with no daemon running, which is exactly the state a
port that will not bind leaves you in, and the audit table is the daemon's.
So the event is not moved, it ends.

The rows it already wrote have to go with it, for the reason 0055 gave when it
purged twenty-seven retired events at once: a row whose ``event_type`` nothing
in the code can name any more is a row every reader has to cope with and none
can label. ``coffer__diagnose`` hands an agent a window of this table when
something has gone wrong with Coffer, and an unnameable event in that window
costs more than the record is worth. Retention would age them out eventually,
and eventually is the wrong answer for the same reason it was then.

The volume is small — the event only ever fired when a person changed the port
through Settings, a panel that existed for one day — so this is tidiness rather
than the relief 0055 was.

The event name is inlined rather than imported. A migration must mean the same
thing forever, and importing the enum would make this revision's behaviour
change with every later release that edits it — precisely the property a
migration must not have. (It could not be imported here in any case: the member
is deleted in the same change.)

Idempotent: a vault that never wrote the event matches no rows. Irreversible by
nature — the downgrade cannot invent rows back, which is acceptable because
they record an event the product no longer has.

Revision ID: 0069
Revises: 0068
Create Date: 2026-09-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0069"
down_revision: str | None = "0068"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The retired ``AuditEventType`` member's stored value, frozen here.
_RETIRED_EVENT = "daemon_port_set"


def upgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM audit_log WHERE event_type = :event"),
        {"event": _RETIRED_EVENT},
    )


def downgrade() -> None:
    """No-op: the deleted rows record an event that no longer exists."""
