"""strip the webhook-era keys off every SeaTalk channel

SeaTalk inbound has one transport now, the outbound websocket connection the
daemon holds (spec channels/seatalk "Receive every event over one outbound
websocket connection"). Webhook delivery — the callback listener, signature
verification, the managed tunnel and the public URL — is deleted, so the four
keys that configured it configure nothing: ``delivery``, ``signing_secret_ref``,
``public_base_url`` and ``tunnel_token_ref``. A stored key that decides nothing
misdescribes the running system, so every SeaTalk channel row loses all four
here (spec channels/seatalk "Configure a SeaTalk channel by app id and secret
reference").

The credential rows the two removed refs cited are left in ``credentials``: a
migration that deletes secrets cannot be undone by its downgrade, and the values
are inert ciphertext that ``coffer credentials delete <ref>`` removes on
purpose.

Idempotent: a row carrying none of the four keys is skipped, so a re-run
matches nothing. The key names are inlined rather than imported — a migration
must mean the same thing forever. A Telegram channel and a row whose config the
app cannot read either are left exactly as found.

Revision ID: 0103
Revises: 0102
Create Date: 2026-09-24
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0103"
down_revision: str | None = "0102"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The ``SeaTalkChannelConfig`` keys this revision retires, frozen here.
_DELIVERY = "delivery"
_RETIRED = (_DELIVERY, "signing_secret_ref", "public_base_url", "tunnel_token_ref")


def _seatalk_rows() -> list[tuple[int, dict[str, object]]]:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, config_json FROM resources WHERE kind = 'channel'")
    ).fetchall()
    out: list[tuple[int, dict[str, object]]] = []
    for row_id, raw in rows:
        try:
            config = json.loads(raw)
        except (TypeError, ValueError):
            continue  # a row the app cannot read either; not this script's to fix
        if isinstance(config, dict) and config.get("channel_type") == "seatalk":
            out.append((row_id, config))
    return out


def _write(row_id: int, config: dict[str, object]) -> None:
    op.get_bind().execute(
        sa.text("UPDATE resources SET config_json = :cfg WHERE id = :id"),
        {"cfg": json.dumps(config), "id": row_id},
    )


def upgrade() -> None:
    for row_id, config in _seatalk_rows():
        dropped = [key for key in _RETIRED if config.pop(key, ...) is not ...]
        if dropped:
            _write(row_id, config)


def downgrade() -> None:
    """Write ``delivery: "websocket"`` onto every SeaTalk channel.

    The model below this revision defaults ``delivery`` to ``webhook`` and then
    requires a signing secret the upgrade removed, so a plain inverse would
    leave every SeaTalk row unreadable by the older build. ``websocket`` is both
    readable there and true of the channel. The signing-secret ref, public URL
    and tunnel token are not recoverable and nothing above reads them.
    """
    for row_id, config in _seatalk_rows():
        if config.get(_DELIVERY) == "websocket":
            continue
        config[_DELIVERY] = "websocket"
        _write(row_id, config)
