"""Reading ``coffer.db`` once, at revision 0135, for the upgrade.

This is the only code in the build that reads the tables whose state moves
into files (the upgrade step itself; plan q9 D15). It reads the database
with the standard library, never through the ORM — the models of
those tables are gone from this build — and answers plain rows keyed to uids,
so the exporters never see an integer ``resources.id``.

Timestamps are handed on as the text SQLite holds; each exporter parses them
where the store it writes for needs a ``datetime``.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from coffer.domain.scope import Scope, ScopeValidationError


@dataclass(frozen=True)
class OldResource:
    uid: str
    kind: str
    name: str
    description: str | None
    title: str | None
    config: dict[str, Any]
    enabled: bool
    scope: Scope | None


Row = dict[str, Any]


@dataclass
class LegacyState:
    """Every row the upgrade carries, and every one it could not."""

    resources: list[OldResource] = field(default_factory=list)
    secrets: list[Row] = field(default_factory=list)
    secret_bindings: list[Row] = field(default_factory=list)
    secret_approvals: list[Row] = field(default_factory=list)
    secret_settings: dict[str, str] = field(default_factory=dict)
    #: ``(server uid, type, key, enabled, first seen, last seen)`` rows.
    capabilities: list[Row] = field(default_factory=list)
    peers: list[Row] = field(default_factory=list)
    engine: Row | None = None
    retention: list[Row] = field(default_factory=list)
    source_status: list[Row] = field(default_factory=list)
    tool_reach: list[Row] = field(default_factory=list)
    health: list[Row] = field(default_factory=list)
    skill_bindings: list[Row] = field(default_factory=list)
    sync_remote: Row | None = None
    #: What could not be carried, one line each, for the report.
    skipped: list[str] = field(default_factory=list)

    def name_of(self, uid: str) -> str | None:
        return next((r.name for r in self.resources if r.uid == uid), None)


@contextlib.contextmanager
def _open(path: Path) -> Iterator[sqlite3.Connection]:
    # Not ``mode=ro``: a WAL database whose ``-shm`` is gone cannot be opened
    # read-only. Nothing here writes, and the file was backed up first.
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _rows(conn: sqlite3.Connection, tables: set[str], table: str) -> list[Row]:
    if table not in tables:
        return []
    return [dict(r) for r in conn.execute(f"SELECT * FROM {table}")]


#: Config keys a kind has retired, frozen as of this build. The upgrade drops
#: them while it reads, so the file it writes is one the kind's model accepts
#: (``MCPServerConfig`` refuses undeclared keys; no idle collector was ever
#: built, so ``idle_timeout_seconds`` decided nothing).
_RETIRED_CONFIG_KEYS: dict[str, tuple[str, ...]] = {"mcp_server": ("idle_timeout_seconds",)}


def _resource(row: Row, skipped: list[str]) -> OldResource | None:
    label = f"{row['kind']} {row['name']}"
    if not row.get("uid"):
        skipped.append(f"resource {label}: no uid")
        return None
    try:
        config = json.loads(row["config_json"])
    except (TypeError, ValueError):
        skipped.append(f"resource {label}: config is not JSON")
        return None
    if not isinstance(config, dict):
        skipped.append(f"resource {label}: config is not an object")
        return None
    for key in _RETIRED_CONFIG_KEYS.get(row["kind"], ()):
        config.pop(key, None)
    scope: Scope | None = None
    if row.get("scope_json"):
        try:
            scope = Scope.from_json(json.loads(row["scope_json"]))
        except (ValueError, ScopeValidationError):
            skipped.append(f"resource {label}: scope unreadable, reach reset to the default")
    return OldResource(
        uid=row["uid"],
        kind=row["kind"],
        name=row["name"],
        description=row.get("description"),
        title=row.get("title") or None,
        config=config,
        enabled=bool(row.get("enabled", 1)),
        scope=scope,
    )


def _rekey(rows: list[Row], column: str, uids: dict[int, str], skipped: list[str], what: str):  # type: ignore[no-untyped-def]
    out: list[Row] = []
    for row in rows:
        uid = uids.get(row.pop(column))
        if uid is None:
            skipped.append(f"{what}: row of a resource that no longer exists")
            continue
        out.append({"uid": uid, **row})
    return out


def read_legacy(db: Path) -> LegacyState:
    """Everything in ``db`` (at revision 0135) that moves out of it."""
    state = LegacyState()
    with _open(db) as conn:
        tables = _tables(conn)
        uids: dict[int, str] = {}
        for row in _rows(conn, tables, "resources"):
            found = _resource(row, state.skipped)
            if found is not None:
                state.resources.append(found)
                uids[int(row["id"])] = found.uid
        state.secrets = _rows(conn, tables, "secrets")
        state.secret_bindings = _rows(conn, tables, "secret_bindings")
        state.secret_approvals = _rows(conn, tables, "secret_approvals")
        state.secret_settings = {
            str(r["key"]): str(r["value"]) for r in _rows(conn, tables, "secret_boundary_settings")
        }
        state.capabilities = _rekey(
            _rows(conn, tables, "mcp_capability_preferences"),
            "resource_id",
            uids,
            state.skipped,
            "capability switch",
        )
        state.peers = _rekey(
            _rows(conn, tables, "channel_peers"), "resource_id", uids, state.skipped, "channel peer"
        )
        engine = _rows(conn, tables, "internal_engine_config")
        state.engine = engine[0] if engine else None
        state.retention = _rows(conn, tables, "retention_policies")
        state.source_status = _rekey(
            _rows(conn, tables, "skill_source_status"),
            "skill_resource_id",
            uids,
            state.skipped,
            "skill source status",
        )
        state.tool_reach = _rows(conn, tables, "mcp_tool_reach")
        state.health = _rows(conn, tables, "mcp_server_health")
        for row in _rows(conn, tables, "skill_agent_bindings"):
            skill = uids.get(row.pop("skill_resource_id"))
            agent = uids.get(row.pop("agent_resource_id"))
            if skill is None or agent is None:
                state.skipped.append("skill delivery: row of a resource that no longer exists")
                continue
            state.skill_bindings.append({"skill_uid": skill, "agent_uid": agent, **row})
        remote = _rows(conn, tables, "sync_remotes")
        state.sync_remote = remote[0] if remote else None
    return state


__all__ = ["LegacyState", "OldResource", "Row", "read_legacy"]
