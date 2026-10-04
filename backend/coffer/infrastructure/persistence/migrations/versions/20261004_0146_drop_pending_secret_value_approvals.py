"""drop ``add_secret`` and ``replace_value`` approvals from ``local/secret-boundary/approvals.json``

A secret's value is stored at once now, a new standalone secret and a
replacement alike (spec secret "Store a secret through the API"). The two
approval kinds that held such a value, sealed, until a person approved it are
gone, so a row of either kind left in the file, and the sealed value it
carries, has nothing to apply or show. Every such row is removed, decided or
not. Approvals for a new destination and for turning the protection off stay.

Data-only, and it touches no table: the file lives beside this database
(``~/.coffer/local``). A database with no directory to look in (``:memory:``),
or a home with no such file, is left alone.

Idempotent: a second run finds no such row.

Revision ID: 0146
Revises: 0145
Create Date: 2026-10-04
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Sequence

from alembic import op

revision: str = "0146"
down_revision: str | None = "0145"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DROPPED = ("add_secret", "replace_value")


def _approvals_file() -> pathlib.Path | None:
    database = op.get_bind().engine.url.database
    if not database or database == ":memory:":
        return None
    return pathlib.Path(database).parent / "local" / "secret-boundary" / "approvals.json"


def upgrade() -> None:
    path = _approvals_file()
    if path is None or not path.is_file():
        return
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = doc.get("approvals", [])
    kept = [r for r in rows if r.get("op") not in _DROPPED]
    if len(kept) != len(rows):
        doc["approvals"] = kept
        path.write_text(
            json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )


def downgrade() -> None:
    """Nothing to put back: the dropped approvals were unanswered questions."""
