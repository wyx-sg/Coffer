"""materialise connections' compatible_agents into the framework scope

Revision ID: 0071
Revises: 0070
Create Date: 2026-09-13

``provider`` grew the framework's per-agent scope (ADR per-agent-resource-scope), which replaces
the kind-specific "which agents" axis it carried inside its own config as
``config_json -> compatible_agents``. The two axes disagree on what UNSET means,
and that disagreement is the whole reason this migration exists:

  - ``compatible_agents = null`` meant "the default for this wire" — for an
    ``ollama`` connection, NO agent at all.
  - framework ``scope = null`` means "every agent".

So the old value cannot simply be renamed into the new column: a null would
flip an internal-only ollama connection into both coding agents, and a
never-narrowed anthropic connection would stop being distinguishable from one
the user deliberately opened up. Every row is therefore MATERIALISED — the
effective set is computed and written out concretely — so the reach of every
existing connection is bit-for-bit what it was before the upgrade. The now-dead
``compatible_agents`` key is then stripped from the config, because
``ProviderConfig`` forbids unknown keys and would refuse to load the row
(the repo leaves no load-time shims behind: the data is cleaned here instead).

The resolution is the one ``ProviderConfig.resolved_compatible_agents`` did:
an explicit list is deduped, order preserving; ``null``/absent falls back to
the wire default. Both are inlined and frozen below — migration scripts never
import application code, which can change under them (revision 0051 is the
house example).

``downgrade`` writes the scope back into ``compatible_agents`` and clears the
scope column, which round-trips every row this upgrade touched: the effective
set is what the old field stored, so no information is lost in either
direction. It writes the set out explicitly rather than trying to recover which
rows had been relying on the wire default — the reach is preserved, the
"I never chose" bit is not, and reach is the half anything reads.

Idempotence takes an explicit test, because the obvious loop does not have it.
Once the key is stripped, "no ``compatible_agents``" is indistinguishable from
"never named one" by the config alone — so re-resolving would fall back to the
WIRE DEFAULT and overwrite the materialised value, silently widening exactly the
connection this migration exists to leave alone (and re-waking one deliberately
scoped to ``[]``). The stored scope is the tell: a row with no key and a
non-null ``scope_json`` has already been through here and is skipped, while a
row with no key and a null scope is a genuine pre-scope row that did rely on the
wire default.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0071"
down_revision: str | None = "0070"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Frozen copy of ``_DEFAULT_COMPATIBLE`` as it stood when this revision was
#: written: the effective agent set of a connection that never named one.
_WIRE_DEFAULT: dict[str, list[str]] = {
    "anthropic": ["claude_code", "codex"],
    "openai": ["claude_code", "codex"],
    "ollama": [],
    "unknown": ["claude_code", "codex"],
}
_FALLBACK: list[str] = ["claude_code", "codex"]


def _resolved(config: dict[str, object]) -> list[str]:
    """The effective agent set of one stored connection config."""
    agents = config.get("compatible_agents")
    if not isinstance(agents, list):
        protocol = config.get("protocol")
        key = protocol if isinstance(protocol, str) else ""
        return list(_WIRE_DEFAULT.get(key, _FALLBACK))
    seen: dict[str, None] = {}
    for a in agents:
        if isinstance(a, str):
            seen.setdefault(a, None)
    return list(seen)


def _provider_rows(bind: sa.engine.Connection) -> list[tuple[int, str, str | None]]:
    return [
        (row[0], row[1], row[2])
        for row in bind.execute(
            sa.text("SELECT id, config_json, scope_json FROM resources WHERE kind = 'provider'")
        ).fetchall()
    ]


def _config(raw: str) -> dict[str, object] | None:
    try:
        config = json.loads(raw)
    except (TypeError, ValueError):
        return None  # a row the app cannot read either; not this script's to fix
    return config if isinstance(config, dict) else None


def upgrade() -> None:
    bind = op.get_bind()
    for row_id, raw, scope_raw in _provider_rows(bind):
        config = _config(raw)
        if config is None:
            continue
        if "compatible_agents" not in config and scope_raw is not None:
            continue  # already materialised — see this module's docstring
        scope = _resolved(config)
        config.pop("compatible_agents", None)
        bind.execute(
            sa.text("UPDATE resources SET config_json = :cfg, scope_json = :scope WHERE id = :id"),
            {"cfg": json.dumps(config), "scope": json.dumps(scope), "id": row_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for row_id, raw, scope_raw in _provider_rows(bind):
        config = _config(raw)
        if config is None:
            continue
        try:
            scope = json.loads(scope_raw) if scope_raw else None
        except (TypeError, ValueError):
            scope = None
        # An unscoped row is one this upgrade never reached; the pre-scope
        # world spelled "no explicit choice" as null, so leave it that way.
        config["compatible_agents"] = scope if isinstance(scope, list) else None
        bind.execute(
            sa.text("UPDATE resources SET config_json = :cfg, scope_json = NULL WHERE id = :id"),
            {"cfg": json.dumps(config), "id": row_id},
        )
