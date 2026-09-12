"""give every curated model entry a ``modality``

A connection's curated set used to be a list of bare ids, which silently assumed
every model an endpoint serves is a chat model. It is not: the same credential
reaches embedding, image, video and speech models, and the global embedding
setting now picks one of them from a connection the same way the internal engine
picks a chat model (spec provider-switching FR-029). So each entry becomes
``{"id": ..., "modality": ...}``.

Rows written before this revision have no answer for entries they already hold,
and the only evidence available is the id itself — so this revision GUESSES,
once, from the name: ``embed`` ⇒ embedding; ``dall``/``imagen``/``image``/
``flux`` or a bare ``sd``/``sd3``/``sdxl`` token ⇒ image; ``video``/``sora`` or a
``veo`` token ⇒ video; ``whisper``/``audio`` or a ``tts`` token ⇒ audio;
everything else ⇒ text, which is what these sets were curated as. The guess is a
migration convenience and nothing else: from here the STORED modality is the
truth, the user corrects a wrong guess from the connection's model table, and no
load-time shim re-infers anything.

Idempotent: an entry already stored as an object is left exactly as it is, so a
re-run matches nothing. The key names and the inference table are inlined rather
than imported — a migration must mean the same thing forever, and importing the
domain would make this revision's behaviour drift as the domain evolves.

Revision ID: 0064
Revises: 0063
Create Date: 2026-09-12
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0064"
down_revision: str | None = "0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The ``ProviderConfig`` key this revision reshapes, frozen here.
_KEY = "models"

#: Long enough to be unambiguous anywhere in an id.
_SUBSTRINGS: tuple[tuple[str, str], ...] = (
    ("embed", "embedding"),
    ("dall", "image"),
    ("imagen", "image"),
    ("image", "image"),
    ("flux", "image"),
    ("video", "video"),
    ("sora", "video"),
    ("whisper", "audio"),
    ("audio", "audio"),
)

#: Short names that must match a whole token, so an unrelated id keeps ``text``.
_TOKENS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^sd(\d.*|xl.*)?$"), "image"),
    (re.compile(r"^veo\d*$"), "video"),
    (re.compile(r"^tts\d*$"), "audio"),
)

_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


def _infer(model_id: str) -> str:
    name = model_id.strip().lower()
    for needle, modality in _SUBSTRINGS:
        if needle in name:
            return modality
    for token in _TOKEN_SPLIT.split(name):
        if not token:
            continue
        for pattern, modality in _TOKENS:
            if pattern.match(token):
                return modality
    return "text"


def _to_objects(entries: list[object]) -> tuple[list[object], bool]:
    """Plain ids → ``{id, modality}``; already-converted entries pass through."""
    out: list[object] = []
    changed = False
    for entry in entries:
        if isinstance(entry, str):
            out.append({"id": entry, "modality": _infer(entry)})
            changed = True
        else:
            out.append(entry)
    return out, changed


def _to_ids(entries: list[object]) -> tuple[list[object], bool]:
    """``{id, modality}`` → plain ids; already-plain entries pass through."""
    out: list[object] = []
    changed = False
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            out.append(entry["id"])
            changed = True
        else:
            out.append(entry)
    return out, changed


def _rewrite(to_objects: bool) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, config_json FROM resources WHERE kind = 'provider'")
    ).fetchall()
    for row_id, raw in rows:
        try:
            config = json.loads(raw)
        except (TypeError, ValueError):
            continue  # a row the app cannot read either; not this script's to fix
        if not isinstance(config, dict):
            continue
        entries = config.get(_KEY)
        if not isinstance(entries, list):
            continue
        converted, changed = (_to_objects if to_objects else _to_ids)(entries)
        if not changed:
            continue
        config[_KEY] = converted
        bind.execute(
            sa.text("UPDATE resources SET config_json = :cfg WHERE id = :id"),
            {"cfg": json.dumps(config), "id": row_id},
        )


def upgrade() -> None:
    _rewrite(to_objects=True)


def downgrade() -> None:
    """Flatten back to bare ids — the pre-0064 ``ProviderConfig`` accepts only
    those. The modality is lost, which is exactly the information this revision
    added and nothing below it can read."""
    _rewrite(to_objects=False)
