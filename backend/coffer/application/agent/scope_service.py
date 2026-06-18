"""Per-agent MCP server scope management (spec 001/004, ADR-026).

Reads/writes an agent's scope (mode + allowlist) and resolves the effective
allowlist the gateway enforces. Agents and MCP servers are both resources, so
this service translates their names ↔ resource ids around the id-keyed repo.

The repo is typed against a local Protocol (not the concrete infrastructure
class) so the application layer stays free of infrastructure imports; the
composition root injects the real ``AgentMcpScopeRepo``.
"""

from __future__ import annotations

from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.domain.agent.scope import AgentMcpScope, ScopeMode
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import ResourceRef
from coffer.domain.scope_errors import AgentMcpScopeServerUnknown


class AgentMcpScopeRepoPort(Protocol):
    """The id-keyed persistence the scope service needs."""

    async def get_mode(self, agent_resource_id: int) -> str | None: ...
    async def get_allowed_server_ids(self, agent_resource_id: int) -> set[int]: ...
    async def set(self, agent_resource_id: int, mode: str, server_ids: list[int]) -> None: ...


class AgentMcpScopeService:
    """Manage and resolve per-agent MCP server scopes."""

    def __init__(
        self,
        repo: AgentMcpScopeRepoPort,
        resources: ResourceService,
        audit: AuditService,
    ) -> None:
        self._repo = repo
        self._resources = resources
        self._audit = audit

    # --- gateway-facing resolution -------------------------------------- #

    async def allowed_server_names(self, agent_name: str) -> set[str] | None:
        """The allowlist the gateway enforces, or ``None`` when unscoped.

        ``None`` (auto mode, or an unknown agent) means every enabled server is
        exposed. A set means selected mode — only those server names are exposed.
        """
        agent_id = await self._agent_id(agent_name)
        if agent_id is None:
            return None
        mode = await self._repo.get_mode(agent_id)
        if mode != "selected":
            return None
        ids = await self._repo.get_allowed_server_ids(agent_id)
        return set(await self._server_names_for_ids(ids))

    # --- REST-facing read/write ----------------------------------------- #

    async def get_scope(self, agent_name: str) -> AgentMcpScope:
        agent = await self._resources.get(ResourceRef("agent", agent_name))
        mode: ScopeMode = (
            "selected" if await self._repo.get_mode(agent.id) == "selected" else "auto"
        )
        servers: tuple[str, ...] = ()
        if mode == "selected":
            ids = await self._repo.get_allowed_server_ids(agent.id)
            servers = tuple(sorted(await self._server_names_for_ids(ids)))
        return AgentMcpScope(agent_name=agent_name, mode=mode, servers=servers)

    async def set_scope(
        self,
        agent_name: str,
        mode: ScopeMode,
        servers: list[str],
        *,
        actor: str = "api",
    ) -> AgentMcpScope:
        # Resolve the agent first so an unknown agent is a 404 before any write.
        agent = await self._resources.get(ResourceRef("agent", agent_name))
        server_ids: list[int] = []
        if mode == "selected":
            server_ids = await self._resolve_server_ids(servers)
        await self._repo.set(agent.id, mode, server_ids)
        await self._audit.record(
            AuditEventType.AGENT_MCP_SCOPE_SET.value,
            ref=ResourceRef("agent", agent_name),
            actor=actor,
            details={"mode": mode, "servers": sorted(servers) if mode == "selected" else []},
        )
        return await self.get_scope(agent_name)

    # --- helpers --------------------------------------------------------- #

    async def _agent_id(self, agent_name: str) -> int | None:
        try:
            agent = await self._resources.get(ResourceRef("agent", agent_name))
        except ResourceNotFound:
            return None
        return agent.id

    async def _resolve_server_ids(self, names: list[str]) -> list[int]:
        name_to_id = {s.name: s.id for s in await self._resources.list(kind="mcp_server")}
        ids: list[int] = []
        for name in dict.fromkeys(names):  # dedupe, preserve order
            sid = name_to_id.get(name)
            if sid is None:
                raise AgentMcpScopeServerUnknown(name)
            ids.append(sid)
        return ids

    async def _server_names_for_ids(self, ids: set[int]) -> list[str]:
        if not ids:
            return []
        servers = await self._resources.list(kind="mcp_server")
        return [s.name for s in servers if s.id in ids]
