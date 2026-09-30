"""MCP capability switches: a vault document per server, seen-times derived
(plan D13; spec vault-storage).

Whether a person switched a capability off is theirs, and travels: it is
``state/mcp-preferences/<server name>.json``::

    {"server_uid": "<uid>", "format_version": 1, "disabled": {"tool": ["delete_repo"]}}

Only the switched-off capabilities are listed — a capability nobody touched
is on, so a new upstream tool writes nothing into the vault. When this machine
first and last saw each capability is an observation it makes again, so those
times are in ``derived/derived.db`` (``mcp_capability_seen``) and never
committed.

The document follows its server: deleted with it in the same commit (the
server's name is fixed, so it is never renamed; the follower handles a rename
anyway).

The invocation log and the server-health record live in sibling modules and
are re-exported here, so ``persistence`` stays the one import for the kind.
Per Contract 5 (cross-kind imports forbidden), this module must NOT import
from any other kind module.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.mcp.capability import CapabilityType, MCPCapabilityPreference
from coffer.infrastructure.mcp.health_repo import (
    HealthStatus,
    MCPServerHealthModel,
    MCPServerHealthRepo,
)
from coffer.infrastructure.mcp.invocation_writer import (
    MCPInvocationModel,
    MCPInvocationRepo,
)
from coffer.infrastructure.mcp.tool_reach_repo import MCPToolReachStore
from coffer.infrastructure.persistence.derived_db import MCPCapabilitySeenModel
from coffer.infrastructure.vault.state_documents import StateDocuments

__all__ = [
    "AREA",
    "HealthStatus",
    "MCPCapabilityPreferenceStore",
    "MCPInvocationModel",
    "MCPInvocationRepo",
    "MCPServerHealthModel",
    "MCPServerHealthRepo",
    "MCPToolReachStore",
]

#: ``state/mcp-preferences/``.
AREA = "mcp-preferences"
_OWNER = "server_uid"
#: What a capability the person switched off, but this machine has never
#: seen, reports as its seen-times: nothing was observed here.
_NEVER = datetime.fromtimestamp(0, tz=UTC)


def _tz(dt: datetime) -> datetime:
    """Re-attach UTC if SQLite stripped the tzinfo on read-back."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _disabled(doc: dict[str, Any] | None) -> dict[str, set[str]]:
    raw = (doc or {}).get("disabled")
    if not isinstance(raw, dict):
        return {}
    return {
        str(t): {k for k in keys if isinstance(k, str)}
        for t, keys in raw.items()
        if isinstance(keys, list)
    }


class MCPCapabilityPreferenceStore:
    """``MCPCapabilityPreferenceRepoPort``: switches in the vault, seen-times
    in ``derived.db``."""

    def __init__(
        self,
        derived_sm: async_sessionmaker,  # type: ignore[type-arg]
        *,
        name_of: Callable[[str], str | None] = lambda _uid: None,
        home: Path | None = None,
    ) -> None:
        self._sm = derived_sm
        self._name_of = name_of
        self.documents = StateDocuments(AREA, _OWNER, home=home)

    def _off(self, server_uid: str) -> dict[str, set[str]]:
        return _disabled(self.documents.get(server_uid))

    def _save(self, server_uid: str, off: dict[str, set[str]], summary: str) -> None:
        listed = {t: sorted(keys) for t, keys in sorted(off.items()) if keys}
        if not listed:
            self.documents.remove(server_uid, summary=summary)
            return
        name = self._name_of(server_uid) or server_uid
        self.documents.put(server_uid, name, {"disabled": listed}, summary=summary)

    async def _seen(
        self, server_uid: str, capability_type: CapabilityType | None
    ) -> list[MCPCapabilitySeenModel]:
        async with self._sm() as session:
            stmt = select(MCPCapabilitySeenModel).where(
                MCPCapabilitySeenModel.server_uid == server_uid
            )
            if capability_type is not None:
                stmt = stmt.where(MCPCapabilitySeenModel.capability_type == capability_type)
            return list((await session.execute(stmt)).scalars().all())

    async def find(
        self, resource_uid: str, capability_type: CapabilityType, capability_key: str
    ) -> MCPCapabilityPreference | None:
        for pref in await self.list_for(resource_uid, capability_type):
            if pref.capability_key == capability_key:
                return pref
        return None

    async def list_for(
        self, resource_uid: str, capability_type: CapabilityType | None = None
    ) -> list[MCPCapabilityPreference]:
        """Every capability seen here, and every one switched off anywhere."""
        off = self._off(resource_uid)
        out: dict[tuple[str, str], MCPCapabilityPreference] = {}
        for row in await self._seen(resource_uid, capability_type):
            ctype: Any = row.capability_type
            out[(row.capability_type, row.capability_key)] = MCPCapabilityPreference(
                resource_uid=resource_uid,
                capability_type=ctype,
                capability_key=row.capability_key,
                enabled=row.capability_key not in off.get(row.capability_type, set()),
                first_seen_at=_tz(row.first_seen_at),
                last_seen_at=_tz(row.last_seen_at),
            )
        for ctype_name, keys in off.items():
            if capability_type is not None and ctype_name != capability_type:
                continue
            for key in keys:
                if (ctype_name, key) not in out:
                    ct: Any = ctype_name
                    out[(ctype_name, key)] = MCPCapabilityPreference(
                        resource_uid=resource_uid,
                        capability_type=ct,
                        capability_key=key,
                        enabled=False,
                        first_seen_at=_NEVER,
                        last_seen_at=_NEVER,
                    )
        return [out[k] for k in sorted(out)]

    async def _touch(
        self, server_uid: str, capability_type: str, keys: list[str], when: datetime
    ) -> list[str]:
        """Record ``keys`` as seen at ``when``; answer the ones new here."""
        if not keys:
            return []
        async with self._sm() as session:
            existing = set(
                (
                    await session.execute(
                        select(MCPCapabilitySeenModel.capability_key).where(
                            MCPCapabilitySeenModel.server_uid == server_uid,
                            MCPCapabilitySeenModel.capability_type == capability_type,
                            MCPCapabilitySeenModel.capability_key.in_(keys),
                        )
                    )
                )
                .scalars()
                .all()
            )
            if existing:
                await session.execute(
                    update(MCPCapabilitySeenModel)
                    .where(
                        MCPCapabilitySeenModel.server_uid == server_uid,
                        MCPCapabilitySeenModel.capability_type == capability_type,
                        MCPCapabilitySeenModel.capability_key.in_(existing),
                    )
                    .values(last_seen_at=when)
                )
            new_keys = [k for k in dict.fromkeys(keys) if k not in existing]
            if new_keys:
                await session.execute(
                    sqlite_insert(MCPCapabilitySeenModel)
                    .values(
                        [
                            {
                                "server_uid": server_uid,
                                "capability_type": capability_type,
                                "capability_key": key,
                                "first_seen_at": when,
                                "last_seen_at": when,
                            }
                            for key in new_keys
                        ]
                    )
                    .on_conflict_do_nothing()
                )
            await session.commit()
            return new_keys

    async def insert(
        self,
        resource_uid: str,
        capability_type: CapabilityType,
        capability_key: str,
        enabled: bool,
        first_seen_at: datetime,
        last_seen_at: datetime,
    ) -> MCPCapabilityPreference:
        await self._touch(resource_uid, capability_type, [capability_key], last_seen_at)
        if not enabled:
            off = self._off(resource_uid)
            off.setdefault(capability_type, set()).add(capability_key)
            self._save(resource_uid, off, f"Switched off {capability_type} {capability_key}")
        found = await self.find(resource_uid, capability_type, capability_key)
        assert found is not None
        return found

    async def set_enabled(
        self,
        resource_uid: str,
        capability_type: CapabilityType,
        capability_key: str,
        enabled: bool,
    ) -> MCPCapabilityPreference | None:
        if await self.find(resource_uid, capability_type, capability_key) is None:
            return None
        off = self._off(resource_uid)
        keys = off.setdefault(capability_type, set())
        if enabled:
            keys.discard(capability_key)
        else:
            keys.add(capability_key)
        verb = "on" if enabled else "off"
        self._save(resource_uid, off, f"Switched {verb} {capability_type} {capability_key}")
        return await self.find(resource_uid, capability_type, capability_key)

    async def reconcile(
        self,
        resource_uid: str,
        capability_type: CapabilityType,
        current_keys: list[str],
        *,
        default_enabled: bool,
        when: datetime,
    ) -> list[str]:
        """Record every key as seen now; answer the ones first seen here.

        A new key is on unless ``default_enabled`` is False, in which case it
        is switched off in the server's document. Keys that disappeared
        upstream keep their switch, so a capability that comes back comes back
        as the person left it.
        """
        new_keys = await self._touch(resource_uid, capability_type, current_keys, when)
        if new_keys and not default_enabled:
            off = self._off(resource_uid)
            off.setdefault(capability_type, set()).update(new_keys)
            self._save(resource_uid, off, f"Switched off {len(new_keys)} new {capability_type}s")
        return new_keys
