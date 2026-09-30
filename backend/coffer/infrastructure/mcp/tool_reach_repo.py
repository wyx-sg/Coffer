"""``mcp_tool_reach``: custom tools' machine-local reach overrides (migration 0115).

Implements ``application.mcp.custom_tool_ports.ToolReachRepoPort``. Keyed by
the group's **uid** and the tool's name, so a group keeps its overrides as its
config changes; not part of any synced document (spec vault-sync "Keep reach
machine-local").
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import TIMESTAMP, String, Text, delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from coffer.infrastructure.persistence.base import Base


class MCPToolReachModel(Base):
    __tablename__ = "mcp_tool_reach"

    resource_uid: Mapped[str] = mapped_column(String, primary_key=True)
    tool: Mapped[str] = mapped_column(String, primary_key=True)
    agents_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class MCPToolReachRepo:
    def __init__(self, sm: async_sessionmaker) -> None:  # type: ignore[type-arg]
        self._sm = sm

    async def overrides_for(self, resource_uids: Sequence[str]) -> dict[str, dict[str, list[str]]]:
        if not resource_uids:
            return {}
        async with self._sm() as session:
            stmt = select(MCPToolReachModel).where(
                MCPToolReachModel.resource_uid.in_(list(resource_uids))
            )
            rows = (await session.execute(stmt)).scalars().all()
        out: dict[str, dict[str, list[str]]] = {}
        for row in rows:
            agents = json.loads(row.agents_json)
            out.setdefault(row.resource_uid, {})[row.tool] = [str(a) for a in agents]
        return out

    async def set_override(self, resource_uid: str, tool: str, agents: list[str] | None) -> None:
        async with self._sm() as session:
            if agents is None:
                await session.execute(
                    delete(MCPToolReachModel).where(
                        MCPToolReachModel.resource_uid == resource_uid,
                        MCPToolReachModel.tool == tool,
                    )
                )
            else:
                payload = json.dumps(list(agents))
                now = datetime.now(tz=UTC)
                await session.execute(
                    sqlite_insert(MCPToolReachModel)
                    .values(
                        resource_uid=resource_uid, tool=tool, agents_json=payload, updated_at=now
                    )
                    .on_conflict_do_update(
                        index_elements=["resource_uid", "tool"],
                        set_={"agents_json": payload, "updated_at": now},
                    )
                )
            await session.commit()

    async def delete_tools(self, resource_uid: str, tools: Sequence[str]) -> None:
        if not tools:
            return
        async with self._sm() as session:
            await session.execute(
                delete(MCPToolReachModel).where(
                    MCPToolReachModel.resource_uid == resource_uid,
                    MCPToolReachModel.tool.in_(list(tools)),
                )
            )
            await session.commit()

    async def delete_group(self, resource_uid: str) -> None:
        async with self._sm() as session:
            await session.execute(
                delete(MCPToolReachModel).where(MCPToolReachModel.resource_uid == resource_uid)
            )
            await session.commit()


__all__ = ["MCPToolReachModel", "MCPToolReachRepo"]
