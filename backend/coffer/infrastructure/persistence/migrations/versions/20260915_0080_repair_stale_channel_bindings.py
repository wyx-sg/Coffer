"""bind channels whose ``runs_on`` names nothing this vault can recognise

0079 bound every channel that carried no ``runs_on`` to this machine, and left
a channel that already carried one exactly as found — so as never to drag back
a binding the user had chosen by hand. That rule is right and its premise was
wrong: ``runs_on`` was not a new key on every vault.

The retired machine axis (removed in #382) wrote machine identity as a **ULID**
into resource config, and on at least one real vault a `channel` has carried
``runs_on: 01K…`` since 2026-07-10 — a fossil of a feature that no longer
exists. To 0079 that read as a deliberate binding and was preserved; to the
runtime gate it reads as "another machine's id", which fails closed. The
channel went dark on upgrade, silently, which is the one outcome the binding
was introduced to prevent.

So this pass repairs what 0079 could not tell apart. A machine id today is
``ID_LENGTH`` lowercase hex characters (``domain.sync.machine.derive_machine_id``
— a sha256 digest, truncated); a ULID is 26 of Crockford's base32 and can never
be mistaken for one. A value that cannot be a machine id was not a binding
anybody made, so it is replaced with this machine — the same answer 0079 would
have given had the key not been there at all, and the same behaviour the vault
had the moment before the upgrade.

What it does NOT touch: a well-formed id that names another machine. That is a
real binding, possibly to a machine this vault has not converged with yet, and
guessing there would be exactly the overwrite 0079 was right to refuse.

The shape test is inlined rather than imported, as 0077/0078/0079 were and for
the same reason: a migration must keep meaning the same thing even after the
constant it was written against moves or goes.

Revision ID: 0080
Revises: 0079
Create Date: 2026-09-15
"""

from __future__ import annotations

import json
import pathlib
import re
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0080"
down_revision: str | None = "0079"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FIELD = "runs_on"
_DAEMON_CONFIG = "daemon-config.json"
_MACHINE_ID = "machine_id"

#: What a machine id looks like today: ``derive_machine_id`` returns the first
#: 16 characters of a sha256 hex digest. Frozen here on purpose.
_MACHINE_ID_SHAPE = re.compile(r"\A[0-9a-f]{16}\Z")


def _channel_rows() -> list[tuple[int, str]]:
    bind = op.get_bind()
    return [
        (row[0], row[1])
        for row in bind.execute(
            sa.text("SELECT id, config_json FROM resources WHERE kind = 'channel'")
        ).fetchall()
    ]


def _write(row_id: int, config: Any) -> None:
    op.get_bind().execute(
        sa.text("UPDATE resources SET config_json = :config WHERE id = :id"),
        {"config": json.dumps(config, sort_keys=True), "id": row_id},
    )


def _this_machine_id() -> str | None:
    """The id cached beside this database, or ``None`` when unreadable."""
    bind = op.get_bind()
    database = bind.engine.url.database
    if not database or database == ":memory:":
        return None
    try:
        payload = json.loads((pathlib.Path(database).parent / _DAEMON_CONFIG).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    cached = payload.get(_MACHINE_ID)
    if isinstance(cached, str) and cached.strip():
        return cached.strip()
    return None


def upgrade() -> None:
    """Replace a ``runs_on`` that cannot be a machine id with this machine."""
    machine_id = _this_machine_id()
    if machine_id is None:
        return
    for row_id, raw in _channel_rows():
        try:
            config = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(config, dict):
            continue
        current = config.get(_FIELD)
        if isinstance(current, str) and _MACHINE_ID_SHAPE.match(current):
            continue  # a real binding, this machine's or another's
        _write(row_id, {**config, _FIELD: machine_id})


def downgrade() -> None:
    """Nothing to undo.

    The value this replaced named a machine identity scheme that no longer
    exists, so putting it back would restore a binding no build below this
    revision can act on either. Down there the key is inert, which is what it
    already was when it came from the retired axis.
    """
