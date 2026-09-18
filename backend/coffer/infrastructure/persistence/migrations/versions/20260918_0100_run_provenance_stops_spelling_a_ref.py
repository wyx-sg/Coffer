"""A run's template provenance stops spelling a deleted identity form.

``workflow_runs.template_ref`` held ``workflow:<name>`` — the ``<kind>:<name>``
string form that this release deletes along with the value object behind it
(ADR resource-identity-is-an-immutable-uid). The column was never a foreign
key and is documented as provenance only (spec workflow FR-010): the frozen
``template_snapshot`` beside it is what a run actually executes, and the two
surfaces that read this one render it raw, as a run's subtitle and as a column
in the runs table.

So the prefix was never doing any work. What it was doing is teaching a reader
a spelling of identity that no longer resolves to anything — the worse of the
two outcomes, because a ref is the one thing a reader might reasonably try to
look up. The label alone says what it means: *this run was started from the
template that was called this*, frozen at creation and allowed to go stale.

Only rows whose value begins with ``workflow:`` are touched, so running this
twice is a no-op, and a row some other build wrote is left alone rather than
guessed at.

The downgrade puts the prefix back. It is reversible because the kind is
constant — every row in this table came from a ``workflow`` template — which is
exactly why the prefix carried no information in the first place.

Revision ID: 0100
Revises: 0099
"""

from __future__ import annotations

from alembic import op

revision: str = "0100"
down_revision: str | None = "0099"
branch_labels: str | None = None
depends_on: str | None = None

_PREFIX = "workflow:"


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE workflow_runs
           SET template_ref = SUBSTR(template_ref, {len(_PREFIX) + 1})
         WHERE template_ref LIKE '{_PREFIX}%'
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE workflow_runs
           SET template_ref = '{_PREFIX}' || template_ref
         WHERE template_ref IS NOT NULL
           AND template_ref NOT LIKE '{_PREFIX}%'
        """
    )
