"""delete ``vault/memory-triggers/``

Memory triggers are gone (spec memory "Install delivery hooks explicitly and
removably"): the hook no longer denies a shell command or adds error context,
so the authored guards under ``vault/memory-triggers/`` decide nothing. The
directory is removed, files and all, rather than left to claim for ever that a
trap is guarded.

Data-only, and it touches no table: the files live in the vault beside this
database (``~/.coffer/vault``). The vault scanner finds the deletion on its
next scan, as git sees it against ``HEAD``, and commits it like any other
change a person makes on disk. A database with no directory to look in
(``:memory:``), or a home with no such directory, is left alone.

Idempotent: a second run finds nothing to delete.

Revision ID: 0142
Revises: 0141
Create Date: 2026-10-04
"""

from __future__ import annotations

import pathlib
import shutil
from collections.abc import Sequence

from alembic import op

revision: str = "0142"
down_revision: str | None = "0141"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _triggers_dir() -> pathlib.Path | None:
    database = op.get_bind().engine.url.database
    if not database or database == ":memory:":
        return None
    return pathlib.Path(database).parent / "vault" / "memory-triggers"


def upgrade() -> None:
    path = _triggers_dir()
    if path is not None and path.is_dir():
        shutil.rmtree(path)


def downgrade() -> None:
    """Nothing to put back: the triggers were authored text nothing reads."""
