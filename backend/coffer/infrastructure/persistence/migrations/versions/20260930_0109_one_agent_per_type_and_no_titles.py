"""one agent per type, named by it; no title on agents, MCP servers or skills

Two changes to the ``resources`` rows (spec agent-registry "Keep one agent per
type, named by it", spec resource-framework "Carry an optional editable title on
the kinds that have one"):

1. **Agents collapse to one per type.** A machine could hold two Claude Code
   agents on different config directories; it now holds one, named by its type
   (``claude-code``, ``codex``) with no title and no description. For each type
   with more than one row the migration keeps ONE and drops the others, ranked:

   - the row whose agent's own Coffer MCP entry speaks for it (its
     ``--agent-uid``) — the agent that is actually connected — first;
   - then an enabled row over a disabled one;
   - then the most recently used: the latest of its ``updated_at`` and its
     newest audit entry;
   - then the one on the type's standard directory, then the oldest.

   Every reference another row holds to a dropped agent is re-pointed at the
   kept one, so nothing that reached the type stops reaching it: a reach list
   (``scope_json`` ``agents``) swaps the dropped uid for the kept one without
   duplicating it, and a channel's ``default_agent`` moves likewise. A dropped
   row's skill deliveries are deleted with it (the next reconcile delivers the
   kept agent's). What the dropped agent's own config directory still holds of
   Coffer's — its MCP entry, delivered skill links — is left on disk: a
   migration does not write into an agent's files, and the directory is no
   longer an agent Coffer manages. Each dropped row is logged as
   ``migration.0109.agent_dropped`` with its type, name, uid, directory and the
   uid kept in its place.

   The kept row is renamed to its type's name and loses its description. A row
   whose config names no supported type is left untouched and logged: the model
   refuses it at load either way.

2. **Titles go from three kinds.** ``title`` is cleared on every ``agent``,
   ``mcp_server`` and ``skill`` row; the column stays for the kinds that keep
   one. Nothing reads it back for these kinds, so there is no load-time shim.

The downgrade restores neither dropped rows nor cleared titles: they are not
recoverable, and an older build reads the collapsed rows as ordinary agents.

Revision ID: 0109
Revises: 0108
Create Date: 2026-09-30
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import op

revision: str = "0109"
down_revision: str | None = "0108"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

#: Each supported type's value, its one name and its standard directory under
#: the home directory. Written out rather than imported so this revision keeps
#: meaning what it meant when a later build renames or adds a type.
_TYPES: dict[str, tuple[str, str]] = {
    "claude_code": ("claude-code", ".claude"),
    "codex": ("codex", ".codex"),
}

_UNTITLED_KINDS = ("agent", "mcp_server", "skill")


def _config(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _config_dir(agent_type: str, config: dict[str, Any]) -> Path:
    override = config.get("config_dir")
    if isinstance(override, str) and override:
        return Path(override).expanduser()
    return Path.home() / _TYPES[agent_type][1]


def _connected_uid(agent_type: str, config_dir: Path) -> str | None:
    """The ``--agent-uid`` of the Coffer MCP entry in this directory's agent
    config, read-only; ``None`` when there is none or it cannot be read.

    Best effort by design: the answer only orders duplicates, so any failure
    to read reads as "not connected" rather than failing the upgrade.
    """
    try:
        from coffer.domain.agent.config_files import spec_for
        from coffer.domain.agent.descriptor import descriptor_for
        from coffer.domain.agent.mcp_install import installed_agent_uid
        from coffer.domain.agent.types import AgentType

        descriptor = descriptor_for(AgentType(agent_type))
        if descriptor.mcp is None:
            return None
        spec = spec_for(AgentType(agent_type), descriptor.mcp.config_key, config_dir)
        text = Path(spec.path).read_text(encoding="utf-8")
        return installed_agent_uid(
            descriptor.mcp.format, text, container_key=descriptor.mcp.container_key
        )
    except Exception:
        return None


def _stamp(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def _choose(bind: sa.engine.Connection, agent_type: str, rows: list[Any]) -> Any:
    """The row to keep among one type's agents — see this module's docstring."""
    standard = Path.home() / _TYPES[agent_type][1]

    def rank(row: Any) -> tuple[bool, bool, str, bool]:
        config_dir = _config_dir(agent_type, _config(row.config_json))
        last_audit = bind.execute(
            sa.text("SELECT MAX(timestamp) FROM audit_log WHERE resource_id = :id"),
            {"id": row.id},
        ).scalar()
        return (
            _connected_uid(agent_type, config_dir) == row.uid,
            bool(row.enabled),
            max(_stamp(row.updated_at), _stamp(last_audit)),
            config_dir == standard,
        )

    # Oldest first, then a STABLE sort on the rank: equal ranks keep the oldest.
    oldest_first = sorted(rows, key=lambda r: _stamp(r.created_at))
    return sorted(oldest_first, key=rank, reverse=True)[0]


def _repoint(bind: sa.engine.Connection, replaced: dict[str, str]) -> None:
    """Re-point every reach list and channel default at the kept agents."""
    if not replaced:
        return
    for row in bind.execute(
        sa.text("SELECT id, scope_json FROM resources WHERE scope_json IS NOT NULL")
    ).fetchall():
        try:
            scope = json.loads(row.scope_json)
        except (TypeError, ValueError):
            continue
        agents = scope.get("agents") if isinstance(scope, dict) else None
        if not isinstance(agents, list) or not any(a in replaced for a in agents):
            continue
        mapped: list[Any] = []
        for entry in agents:
            target = replaced.get(entry, entry)
            if target not in mapped:
                mapped.append(target)
        # Never ``None``: an empty list is dormant, ``None`` is every agent.
        scope["agents"] = mapped
        bind.execute(
            sa.text("UPDATE resources SET scope_json = :scope WHERE id = :id"),
            {"scope": json.dumps(scope), "id": row.id},
        )
    for row in bind.execute(
        sa.text("SELECT id, config_json FROM resources WHERE kind = 'channel'")
    ).fetchall():
        config = _config(row.config_json)
        current = config.get("default_agent")
        if isinstance(current, str) and current in replaced:
            config["default_agent"] = replaced[current]
            bind.execute(
                sa.text("UPDATE resources SET config_json = :config WHERE id = :id"),
                {"config": json.dumps(config), "id": row.id},
            )


def _collapse_agents(bind: sa.engine.Connection, *, has_bindings: bool) -> None:
    rows = bind.execute(
        sa.text(
            "SELECT id, uid, name, config_json, enabled, created_at, updated_at"
            " FROM resources WHERE kind = 'agent' ORDER BY id"
        )
    ).fetchall()
    by_type: dict[str, list[Any]] = {}
    for row in rows:
        agent_type = _config(row.config_json).get("type")
        if not isinstance(agent_type, str) or agent_type not in _TYPES:
            logger.warning(
                "migration.0109.agent_unknown_type; name=%s uid=%s type=%s",
                row.name,
                row.uid,
                agent_type,
            )
            continue
        by_type.setdefault(agent_type, []).append(row)

    replaced: dict[str, str] = {}
    kept: list[tuple[Any, str]] = []
    for agent_type, group in by_type.items():
        keep = group[0] if len(group) == 1 else _choose(bind, agent_type, group)
        kept.append((keep, agent_type))
        for row in group:
            if row.id == keep.id:
                continue
            replaced[row.uid] = keep.uid
            logger.warning(
                "migration.0109.agent_dropped; type=%s name=%s uid=%s config_dir=%s kept=%s",
                agent_type,
                row.name,
                row.uid,
                _config_dir(agent_type, _config(row.config_json)),
                keep.uid,
            )
            if has_bindings:
                bind.execute(
                    sa.text("DELETE FROM skill_agent_bindings WHERE agent_resource_id = :id"),
                    {"id": row.id},
                )
            bind.execute(sa.text("DELETE FROM resources WHERE id = :id"), {"id": row.id})
    _repoint(bind, replaced)
    # Renamed only once every duplicate is gone, so the type's name is free.
    for row, agent_type in kept:
        bind.execute(
            sa.text("UPDATE resources SET name = :name, description = NULL WHERE id = :id"),
            {"name": _TYPES[agent_type][0], "id": row.id},
        )
    logger.info("migration.0109.agents; kept=%s dropped=%s", len(kept), len(replaced))


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())
    if "resources" not in tables:
        return
    _collapse_agents(bind, has_bindings="skill_agent_bindings" in tables)
    bind.execute(
        sa.text("UPDATE resources SET title = NULL WHERE kind IN :kinds").bindparams(
            sa.bindparam("kinds", expanding=True)
        ),
        {"kinds": list(_UNTITLED_KINDS)},
    )


def downgrade() -> None:
    """Nothing to restore: dropped duplicates and cleared titles are gone, and
    the collapsed rows are ordinary agents to an older build."""
