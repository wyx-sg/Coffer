"""drop skill content-trust scan fields (simplification 4.5)

Revision ID: 0032
Revises: 0031
Create Date: 2026-06-20

The skill content-trust scanning layer is removed (simplification 4.5): the
heuristic risk scan and the acknowledge-to-enable gate go, so ``SkillConfig``
(which is ``extra="forbid"``) no longer carries the scan/risk bookkeeping
fields. A stored ``kind='skill'`` config still holding them would fail to load,
so this data migration strips them from every skill row's ``config_json``.

Keys stripped: ``scan_verdict``, ``scan_findings_count``,
``scan_ruleset_version``, ``last_scanned_at``, ``risk_acknowledged``.

Idempotent: stripping absent keys is a no-op, so a re-run (or a DB stamped
mid-migration) converges.

Migration scripts never import application code — the field names are inlined
here and stay frozen as the model evolves.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: str | None = "0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (field name -> pre-4.5 default) — the default is used by downgrade to make a
# stripped config loadable again under the older extra="forbid" model.
_SCAN_FIELD_DEFAULTS = {
    "scan_verdict": None,
    "scan_findings_count": 0,
    "scan_ruleset_version": None,
    "last_scanned_at": None,
    "risk_acknowledged": False,
}


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, config_json FROM resources WHERE kind = 'skill'")).all()
    for row_id, config_json in rows:
        cfg = json.loads(config_json)
        changed = False
        for key in _SCAN_FIELD_DEFAULTS:
            if key in cfg:
                del cfg[key]
                changed = True
        if changed:
            bind.execute(
                sa.text("UPDATE resources SET config_json = :cfg WHERE id = :id"),
                {"cfg": json.dumps(cfg), "id": row_id},
            )


def downgrade() -> None:
    # Lossy by nature: the verdict/ack history cannot be reconstructed. Re-add
    # the pre-4.5 defaults so a config written for the older extra="forbid"
    # model loads cleanly again.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, config_json FROM resources WHERE kind = 'skill'")).all()
    for row_id, config_json in rows:
        cfg = json.loads(config_json)
        changed = False
        for key, value in _SCAN_FIELD_DEFAULTS.items():
            if key not in cfg:
                cfg[key] = value
                changed = True
        if changed:
            bind.execute(
                sa.text("UPDATE resources SET config_json = :cfg WHERE id = :id"),
                {"cfg": json.dumps(cfg), "id": row_id},
            )
