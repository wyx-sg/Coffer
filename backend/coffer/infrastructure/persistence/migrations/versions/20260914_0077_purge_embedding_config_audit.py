"""drop the audit rows for the embedding configuration that no longer exists

Coffer no longer embeds anything. Knowledge search is ripgrep over the files
and memory recall is a substring scan over facts already in hand; the ranked
retrieval that sat above both, the disposable vector sidecar it kept, and the
``/embeddings`` client that filled it are all gone. This is a deliberate
reduction of a capability that worked, not the removal of something unused —
embeddings may return one day, but nothing in the product asks for them now.

``embedding_config_updated`` outlived its writer by a release. The global
embedding setting and its panel were removed with the knowledge index (ADR
knowledge-is-plain-files), leaving the event in ``AuditEventType`` with nothing
to emit it; 0055 had already frozen it into the live set a few revisions
earlier, so it survived that sweep. With embeddings themselves gone there is no
prospect of another writer, and the member is deleted in this change.

Its rows go with it, for the reason 0055 gave when it purged twenty-seven
retired events at once and 0069 repeated for one: a row whose ``event_type``
nothing in the code can name any more is a row every reader has to cope with
and none can label. ``coffer__diagnose`` hands an agent a window of this table
when something has gone wrong with Coffer, and an unnameable event in that
window costs more than the record is worth.

The volume is small — the audit of the live installation that motivated the
knowledge reduction found ``embedding_config`` had never held a row, so on most
vaults this matches nothing at all.

No table or column is dropped here because none was left to drop: the
``embedding_config`` table went with revision 0066, and the retrieval index was
never in ``coffer.db`` at all — it was a file under ``~/.coffer/index``, which
this change simply stops writing. A user's existing sidecar file is now inert
and may be deleted by hand; nothing reads it.

The event name is inlined rather than imported. A migration must mean the same
thing forever, and importing the enum would make this revision's behaviour
change with every later release that edits it — precisely the property a
migration must not have. (It could not be imported here in any case: the member
is deleted in the same change.)

Idempotent: a vault that never wrote the event matches no rows. Irreversible by
nature — the downgrade cannot invent rows back, which is acceptable because
they record an event the product no longer has.

Revision ID: 0077
Revises: 0076
Create Date: 2026-09-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0077"
down_revision: str | None = "0076"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The retired ``AuditEventType`` member's stored value, frozen here.
_RETIRED_EVENT = "embedding_config_updated"


def upgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM audit_log WHERE event_type = :event"),
        {"event": _RETIRED_EVENT},
    )


def downgrade() -> None:
    """No-op: the deleted rows record an event that no longer exists."""
