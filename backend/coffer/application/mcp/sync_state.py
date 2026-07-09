"""MCP capability preferences as a synced state area (spec 010 slice 7).

Disabling a tool/prompt on one machine is shared intent — the same server on
the other machine should honor it. Docs carry only the DISABLED capabilities
per server (enabled is the default; seen-timestamps stay machine-local).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, cast

from coffer.application.resource_service import ResourceService
from coffer.domain.mcp.capability import CapabilityType, MCPCapabilityPreference

_CAPABILITY_TYPES = {"tool", "resource", "prompt"}

AREA = "mcp-preferences"


class _PrefsPort(Protocol):
    async def list_for(
        self, resource_id: int, capability_type: CapabilityType | None = None
    ) -> list[MCPCapabilityPreference]: ...

    async def set_enabled(
        self,
        resource_id: int,
        capability_type: CapabilityType,
        capability_key: str,
        enabled: bool,
    ) -> MCPCapabilityPreference | None: ...

    async def insert(
        self,
        resource_id: int,
        capability_type: CapabilityType,
        capability_key: str,
        enabled: bool,
        first_seen_at: datetime,
        last_seen_at: datetime,
    ) -> MCPCapabilityPreference: ...


class McpPreferenceSyncState:
    """Implements ``application.sync.ports.SyncedStatePort`` structurally."""

    area = AREA

    def __init__(self, resources: ResourceService, prefs: _PrefsPort) -> None:
        self._resources = resources
        self._prefs = prefs

    async def export_docs(self) -> tuple[list[tuple[str, dict[str, object]]], list[str]]:
        docs: list[tuple[str, dict[str, object]]] = []
        owned: list[str] = []
        for resource in await self._resources.list(kind="mcp_server"):
            owned.append(resource.name)
            disabled = sorted(
                (str(p.capability_type), p.capability_key)
                for p in await self._prefs.list_for(resource.id)
                if not p.enabled
            )
            if disabled:
                docs.append(
                    (
                        resource.name,
                        {
                            "server": resource.name,
                            "disabled": [{"type": t, "key": k} for t, k in disabled],
                        },
                    )
                )
        return docs, owned

    async def import_docs(self, docs: list[tuple[str, dict[str, object]]]) -> list[tuple[str, str]]:
        errors: list[tuple[str, str]] = []
        by_name = {r.name: r.id for r in await self._resources.list(kind="mcp_server")}
        wanted_by_server: dict[str, set[tuple[str, str]]] = {}
        for _path, doc in docs:
            server = str(doc.get("server") or "")
            entries = doc.get("disabled")
            if not server or not isinstance(entries, list):
                continue
            wanted_by_server[server] = {
                (str(e.get("type")), str(e.get("key")))
                for e in entries
                if isinstance(e, dict) and e.get("type") and e.get("key")
            }
        for server, resource_id in by_name.items():
            wanted = wanted_by_server.get(server, set())
            try:
                current = await self._prefs.list_for(resource_id)
                now = datetime.now(tz=UTC)
                seen = {(str(p.capability_type), p.capability_key): p for p in current}
                for key, pref in seen.items():
                    if not pref.enabled and key not in wanted:
                        await self._prefs.set_enabled(
                            resource_id, pref.capability_type, pref.capability_key, True
                        )
                for cap_type, cap_key in wanted:
                    if cap_type not in _CAPABILITY_TYPES:
                        continue  # a future capability type this build ignores
                    typed = cast(CapabilityType, cap_type)
                    existing = seen.get((cap_type, cap_key))
                    if existing is None:
                        await self._prefs.insert(resource_id, typed, cap_key, False, now, now)
                    elif existing.enabled:
                        await self._prefs.set_enabled(resource_id, typed, cap_key, False)
            except Exception as e:
                errors.append((server, str(e)))
        return errors
