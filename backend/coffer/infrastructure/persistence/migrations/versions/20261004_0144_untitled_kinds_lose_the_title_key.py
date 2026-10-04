"""resource files of the kinds that carry no title lose their ``title`` key

``agent``, ``knowledge``, ``mcp_server``, ``memory`` and ``skill`` are shown by
their fixed name (spec resource-framework "Carry an optional editable title on
the kinds that have one"). ``memory`` is the last of them to lose its title;
the vault validator refuses a file that carries a title on such a kind, so a
partition file still holding one would be flagged instead of read. This strips
the key from every resource file of those kinds, in the three classes that hold
resource files (``vault/``, ``local/``, ``derived/``). Nothing reads the key
back for these kinds, so there is no load-time shim.

Data-only, and it touches no table (the ``resources`` table left ``runs.db`` at
0136). The vault scanner finds an edited ``vault/`` file on its next scan and
commits it like any other change made on disk. Only the one key is removed:
the rest of each file is re-encoded the way the vault always writes it (2-space
indent, key order kept, trailing newline). A file that is not a JSON object is
left alone. Idempotent. A database with no directory to look in (``:memory:``)
is left alone.

The downgrade restores nothing: a removed title is not recoverable, and an
older build reads a missing title as "show the name".

Revision ID: 0144
Revises: 0143
Create Date: 2026-10-04
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Sequence

from alembic import op

revision: str = "0144"
down_revision: str | None = "0143"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UNTITLED_KINDS = ("agent", "knowledge", "mcp_server", "memory", "skill")
_CLASS_DIRS = ("vault", "local", "derived")


def _home() -> pathlib.Path | None:
    database = op.get_bind().engine.url.database
    if not database or database == ":memory:":
        return None
    return pathlib.Path(database).parent


def _strip(path: pathlib.Path) -> None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(doc, dict) or "title" not in doc:
        return
    del doc["title"]
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def upgrade() -> None:
    home = _home()
    if home is None:
        return
    for storage in _CLASS_DIRS:
        for kind in _UNTITLED_KINDS:
            directory = home / storage / "resources" / kind
            if directory.is_dir():
                for path in sorted(directory.glob("*.json")):
                    _strip(path)


def downgrade() -> None:
    """Nothing to restore: removed titles are gone, and an older build shows
    the name where a title is absent."""
