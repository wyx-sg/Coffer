"""strip the graduated features' settings from ``daemon-config.json``

Sync, knowledge and memory stopped being experimental features (spec
experimental-features "Declare the experimental features in one registry"):
their registry entries were deleted, and every surface that read their switch
now serves unconditionally. What a machine stored for them is left in the
``features`` object of ``daemon-config.json`` beside this database —
``vault_sync``, ``knowledge`` and ``memory``, each ``true`` or ``false``.

Nothing reads those keys any more, so leaving them would not change what the
daemon does: a stored key the registry does not name is ignored by every read.
They are removed anyway, because a setting that decides nothing should stop
being stated — the file would otherwise go on claiming, for ever, that sync is
switched off on a machine where it is not. Every other key in the file, and
every other key in ``features``, is kept exactly as found.

Data-only, and it touches no table: the settings live in the daemon config
file, not in the database. The file is found beside the database the way
revision 0079 finds it, and is rewritten atomically with mode ``0600``, as the
daemon writes it. A file that is missing, unreadable, not JSON or not an
object, or a ``features`` value that is not an object, is left untouched: a
migration must never fail on a cache it can do without, and a file the daemon
cannot read either is not this script's to repair.

Idempotent: a file with none of the three keys is not rewritten.

Revision ID: 0116
Revises: 0115
Create Date: 2026-09-30
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import tempfile
from collections.abc import Sequence

from alembic import op

revision: str = "0116"
down_revision: str | None = "0115"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DAEMON_CONFIG = "daemon-config.json"
_FEATURES = "features"
_GRADUATED = ("vault_sync", "knowledge", "memory")


def _config_path() -> pathlib.Path | None:
    """``daemon-config.json`` beside this database, or ``None`` for a database
    with no directory to look in (``:memory:``)."""
    database = op.get_bind().engine.url.database
    if not database or database == ":memory:":
        return None
    return pathlib.Path(database).parent / _DAEMON_CONFIG


def _write_0600(path: pathlib.Path, payload: dict[str, object]) -> None:
    """Replace ``path`` atomically, never visible with a mode wider than 0600."""
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp")
    tmp = pathlib.Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(payload, indent=2))
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise
    os.replace(str(tmp), str(path))


def upgrade() -> None:
    """Drop the three graduated keys from ``features``, keeping everything else."""
    path = _config_path()
    if path is None:
        return
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return
    if not isinstance(payload, dict):
        return
    features = payload.get(_FEATURES)
    if not isinstance(features, dict) or not any(key in features for key in _GRADUATED):
        return
    kept = {key: value for key, value in features.items() if key not in _GRADUATED}
    _write_0600(path, {**payload, _FEATURES: kept})


def downgrade() -> None:
    """Nothing to put back.

    What each key held is gone, and no value would be right to invent: a build
    below this revision reads a missing key as "decided by the channel" — on
    for a ``dev`` build, off for ``stable`` — which is the state that build
    gives any machine that never switched the feature.
    """
