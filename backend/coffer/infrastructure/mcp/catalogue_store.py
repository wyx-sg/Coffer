"""The saved catalogue: what each upstream listed last on this machine.

A session answers ``tools/list`` (and the resource and prompt lists) from here
instead of starting every server to ask it; a server is started when a call
needs it (ADR session-subprocess-model). Derived state: a lost table only
means the next list asks the servers again.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from coffer.domain.mcp.capability import CapabilityType
from coffer.infrastructure.persistence.derived_db import MCPCatalogueModel


class McpCatalogueStore:
    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def load(
        self, server_uid: str, capability_type: CapabilityType
    ) -> tuple[str, list[dict[str, Any]]] | None:
        """``(config_hash, items)`` saved for the server, or None."""
        async with self._sm() as session:
            row = await session.get(MCPCatalogueModel, (server_uid, capability_type))
            if row is None:
                return None
            try:
                items = json.loads(row.items_json)
            except ValueError:
                return None
            return row.config_hash, items if isinstance(items, list) else []

    async def save(
        self,
        server_uid: str,
        capability_type: CapabilityType,
        config_hash: str,
        items: list[dict[str, Any]],
    ) -> None:
        values = {
            "server_uid": server_uid,
            "capability_type": capability_type,
            "config_hash": config_hash,
            "items_json": json.dumps(items, separators=(",", ":")),
            "saved_at": datetime.now(tz=UTC),
        }
        async with self._sm() as session:
            stmt = (
                sqlite_insert(MCPCatalogueModel)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["server_uid", "capability_type"],
                    set_={
                        k: v
                        for k, v in values.items()
                        if k not in ("server_uid", "capability_type")
                    },
                )
            )
            await session.execute(stmt)
            await session.commit()


__all__ = ["McpCatalogueStore"]
