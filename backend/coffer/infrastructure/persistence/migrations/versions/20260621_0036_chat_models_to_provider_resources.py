"""migrate chat_models rows to provider resources, then drop chat_models

Revision ID: 0036
Revises: 0035
Create Date: 2026-06-21

Models + providers unified into one "LLM connection" (a ``provider`` resource).
The standalone ``chat_models`` registry is retired: every row becomes a
``kind='provider'`` row in the generic ``resources`` table whose ``config_json``
is a ``ProviderConfig`` payload, then the ``chat_models`` table is dropped.

Mapping (chat_models -> ProviderConfig):
- ``provider``    -> ``wire_format`` (anthropic | openai | ollama)
- ``base_url``    -> ``base_url`` (a per-wire default fills a NULL endpoint)
- ``credential_ref`` -> ``credential_ref`` (forced NULL for ollama, which has no key)
- ``model``       -> ``model``;   ``fast_model`` is NULL (no tier mapping)
- ``is_default``  -> ``internal_default`` (Coffer's internal-engine connection)
- ``is_active``   -> ``false`` (these never projected to an agent before)
- the connection ``name`` is slugified from ``display_name`` (deduped against
  existing provider names and within the migrated set)

Secrets are NOT re-encrypted — the vault rows keyed by ``credential_ref`` are
left untouched and the migrated connection keeps citing the same ref.

Migration scripts never import application code, so the field names, defaults,
and name grammar are inlined here and stay frozen as the model evolves.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: str | None = "0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copies of domain rules (migrations must not import app code).
_NAME_PATTERN = re.compile(r"[^a-zA-Z0-9_.\-]+")
_NAME_MAX_LEN = 64
_DEFAULT_BASE_URL = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com/v1",
    "ollama": "http://localhost:11434",
}


def _slugify(display_name: str, taken: set[str]) -> str:
    """Derive a resource name (``^[a-zA-Z0-9_.-]+$``, <=64) from a display name,
    deduped against ``taken`` (existing + already-assigned provider names)."""
    base = _NAME_PATTERN.sub("-", display_name).strip("-._")[:_NAME_MAX_LEN]
    if not base:
        base = "connection"
    name = base
    i = 2
    while name in taken:
        suffix = f"-{i}"
        name = base[: _NAME_MAX_LEN - len(suffix)] + suffix
        i += 1
    taken.add(name)
    return name


def upgrade() -> None:
    bind = op.get_bind()

    # Tolerate a DB where ``chat_models`` is already absent (e.g. a re-run after
    # this migration dropped it, or a repair that stamped past it) — nothing to
    # migrate or drop, so the upgrade is a clean no-op.
    if not sa.inspect(bind).has_table("chat_models"):
        return

    taken: set[str] = {
        r[0]
        for r in bind.execute(sa.text("SELECT name FROM resources WHERE kind = 'provider'")).all()
    }

    rows = (
        bind.execute(
            sa.text(
                "SELECT display_name, provider, model, credential_ref, base_url, "
                "is_default, created_at, updated_at FROM chat_models"
            )
        )
        .mappings()
        .all()
    )

    for row in rows:
        wire = str(row["provider"])
        base_url = row["base_url"] or _DEFAULT_BASE_URL.get(wire, "")
        # ollama has no key; anthropic/openai keep their existing ref.
        credential_ref = None if wire == "ollama" else row["credential_ref"]
        config = {
            "wire_format": wire,
            "base_url": base_url,
            "credential_ref": credential_ref,
            "model": row["model"],
            "fast_model": None,
            "wire_api": "chat",
            "is_active": False,
            "internal_default": bool(row["is_default"]),
        }
        name = _slugify(str(row["display_name"]), taken)
        bind.execute(
            sa.text(
                "INSERT INTO resources "
                "(kind, name, description, config_json, enabled, created_at, updated_at) "
                "VALUES ('provider', :name, NULL, :config, 1, :created_at, :updated_at)"
            ),
            {
                "name": name,
                "config": json.dumps(config),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        )

    op.drop_table("chat_models")


def downgrade() -> None:
    # Recreate the chat_models table (mirrors revision 0012) so the schema is
    # restored. The data move is one-way: the migrated rows now live as provider
    # resources and are NOT copied back (their shape diverged — fast_model,
    # internal_default, wire_api have no chat_models columns), mirroring other
    # irreversible data migrations in this tree.
    op.create_table(
        "chat_models",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("credential_ref", sa.Text(), nullable=True),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("display_name", name="uq_chat_models_display_name"),
    )
