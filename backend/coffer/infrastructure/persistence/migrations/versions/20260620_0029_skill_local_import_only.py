"""skills become local-import only (drop Git lifecycle, simplification 4.3)

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-20

The live-Git skill lifecycle is removed (simplification 4.3): create-from-Git
fetch, refresh/update, check-for-updates, and pin/unpin all go, so a skill's
``source`` is now always ``local_import`` and the update/pin bookkeeping fields
disappear from ``SkillConfig`` (which is ``extra="forbid"``, so a stored config
still carrying them would fail to load).

This data migration rewrites every ``kind='skill'`` row's ``config_json``:
  * a ``git`` source becomes ``local_import`` with the former Git URL kept as
    ``original_path`` (provenance is preserved; the skill can no longer be
    re-fetched), and
  * the Git-only keys ``update_available`` / ``available_version_hash`` /
    ``last_update_check_at`` / ``pinned`` are stripped.

``last_synced_from_source_at``, ``version_hash``, ``risk_acknowledged`` and the
``scan_*`` fields are SHARED with the local-import path and are left untouched.

Idempotent: stripping absent keys is a no-op and only ``git`` sources are
converted, so a re-run (or a DB stamped mid-migration) converges.

Migration scripts never import application code — the field names are inlined
so the script stays frozen as the model evolves.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GIT_ONLY_KEYS = (
    "update_available",
    "available_version_hash",
    "last_update_check_at",
    "pinned",
)


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, config_json FROM resources WHERE kind = 'skill'")).all()
    for row_id, config_json in rows:
        cfg = json.loads(config_json)
        changed = False

        source = cfg.get("source")
        if isinstance(source, dict) and source.get("type") == "git":
            cfg["source"] = {
                "type": "local_import",
                # Keep the former Git URL as provenance; original_path is
                # informational only (min_length=1) and the URL is non-empty.
                "original_path": source.get("git_url") or "(git source removed)",
            }
            changed = True

        for key in _GIT_ONLY_KEYS:
            if key in cfg:
                del cfg[key]
                changed = True

        if changed:
            bind.execute(
                sa.text("UPDATE resources SET config_json = :cfg WHERE id = :id"),
                {"cfg": json.dumps(cfg), "id": row_id},
            )


def downgrade() -> None:
    # Lossy by nature: a source converted git -> local_import cannot be restored
    # (git_ref/git_subpath were not retained). Re-add the stripped bookkeeping
    # keys with their pre-4.3 defaults so a config written by the older
    # extra="forbid" model is explicit again; the old model also defaulted them,
    # so even rows left untouched load cleanly.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, config_json FROM resources WHERE kind = 'skill'")).all()
    for row_id, config_json in rows:
        cfg = json.loads(config_json)
        defaults = {
            "update_available": False,
            "available_version_hash": None,
            "last_update_check_at": None,
            "pinned": False,
        }
        changed = False
        for key, value in defaults.items():
            if key not in cfg:
                cfg[key] = value
                changed = True
        if changed:
            bind.execute(
                sa.text("UPDATE resources SET config_json = :cfg WHERE id = :id"),
                {"cfg": json.dumps(cfg), "id": row_id},
            )
