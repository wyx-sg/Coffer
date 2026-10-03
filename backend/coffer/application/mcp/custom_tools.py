"""Custom-tool groups: create, read, change and delete groups and their tools.

Spec mcp-gateway "Serve an HTTP API as a group of custom tools", "Switch off or
narrow one custom tool", "Wait for approval before a custom tool sends its
secret" and "Manage custom tools through REST and the Custom tools page"; design
add-http-custom-tools §2, §5, §9.

A group is an ``mcp_server`` resource of the ``http_api`` transport, so every
write goes through :class:`ResourceService` — the kind's validation, the
missing-secret probe, audit and the eviction of live connections come with
it. What is not in the resource row is a tool's reach override (machine-local,
``ToolReachRepoPort``). OpenAPI import and re-import are in
``custom_tool_import``; the page's read model in ``custom_tool_views``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from coffer.application.audit_service import AuditService
from coffer.application.mcp.custom_tool_ports import (
    CustomToolRunnerPort,
    ToolReach,
    ToolReachRepoPort,
    ToolTestOutcome,
)
from coffer.application.mcp.custom_tool_views import GroupView, GroupViewer
from coffer.application.mcp.gateway_tool_gate import http_api_transport
from coffer.application.resource_service import ResourceService
from coffer.application.secret.resolver import SecretResolver
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ConfigValidationError
from coffer.domain.mcp.custom_tool_errors import (
    CustomToolExists,
    CustomToolNotFound,
    NotACustomToolGroup,
)
from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.mcp.secret_target import mcp_destination
from coffer.domain.mcp.server_config import MCPServerConfig
from coffer.domain.resource import Resource
from coffer.domain.scope import Scope
from coffer.domain.secrets import is_valid_secret_name, secret_ref, standalone_name

KIND = "mcp_server"
#: Sentinel for "leave this field as it is" in a partial update.
UNSET: Any = object()


def secret_name_of(ref: str) -> str:
    """The Secrets-page name a header's secret ref points at."""
    return standalone_name(ref) or ref


def split_headers(rows: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    """Header rows ``{name, value | secret}`` -> ``(plain headers, secret_refs)``.

    A secret holds the whole header value, so a row carries a value or a
    secret, never both."""
    plain: dict[str, str] = {}
    refs: dict[str, str] = {}
    for row in rows:
        name, value, secret = row["name"], row.get("value"), row.get("secret")
        if value is not None and secret is not None:
            raise ConfigValidationError(f"header {name!r} has a value and a secret")
        if secret is not None:
            if not is_valid_secret_name(secret):
                raise ConfigValidationError(f"{secret!r} is not a secret name")
            refs[name] = secret_ref(secret)
        else:
            plain[name] = value or ""
    return plain, refs


def _validated(fields: dict[str, Any]) -> HttpApiTransport:
    try:
        return HttpApiTransport.model_validate({**fields, "type": "http_api"})
    except ValidationError as e:
        raise ConfigValidationError(str(e)) from e


def validated_tool(raw: dict[str, Any]) -> HttpApiTool:
    try:
        return HttpApiTool.model_validate(raw)
    except ValidationError as e:
        raise ConfigValidationError(str(e)) from e


class CustomToolService:
    def __init__(
        self,
        *,
        resources: ResourceService,
        audit: AuditService,
        reach: ToolReachRepoPort,
        viewer: GroupViewer,
        resolver: Callable[[], SecretResolver],
        runner: CustomToolRunnerPort,
        clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC),
    ) -> None:
        self._resources = resources
        self._audit = audit
        self._reach = reach
        self._viewer = viewer
        self._resolver = resolver
        self._runner = runner
        self._clock = clock

    # --- reading -----------------------------------------------------------

    async def group(self, name: str) -> tuple[Resource, HttpApiTransport]:
        resource = await self._resources.get_by_name(KIND, name)
        transport = http_api_transport(resource)
        if transport is None:
            raise NotACustomToolGroup(name)
        return resource, transport

    async def list_groups(self) -> list[GroupView]:
        rows = await self._resources.list(kind=KIND)
        groups = [(r, t) for r in rows if (t := http_api_transport(r)) is not None]
        return await self._viewer.views(groups)

    async def view(self, name: str) -> GroupView:
        return (await self._viewer.views([await self.group(name)]))[0]

    # --- groups ------------------------------------------------------------

    async def create_group(
        self,
        *,
        name: str,
        description: str | None,
        base_url: str,
        headers: list[dict[str, Any]],
        timeout_seconds: int,
        agents: list[str] | None,
        tools: list[dict[str, Any]],
        source: dict[str, Any] | None,
        actor: str,
    ) -> GroupView:
        plain, refs = split_headers(headers)
        fields: dict[str, Any] = {
            "base_url": base_url,
            "headers": plain,
            "secret_refs": refs,
            "timeout_seconds": timeout_seconds,
            "tools": tools,
            "source": source,
        }
        transport = _validated(fields)
        config = MCPServerConfig(transport=transport).model_dump(mode="json")
        created = await self._resources.register(KIND, name, config, actor, description)
        if agents is not None:
            await self._resources.update_scope(created.uid, Scope(agents=agents), actor=actor)
        return await self.view(name)

    async def update_group(
        self,
        name: str,
        *,
        actor: str,
        description: Any = UNSET,
        base_url: Any = UNSET,
        headers: Any = UNSET,
        timeout_seconds: Any = UNSET,
    ) -> GroupView:
        resource, transport = await self.group(name)
        fields = transport.model_dump(mode="json")
        for key, value in (
            ("base_url", base_url),
            ("timeout_seconds", timeout_seconds),
        ):
            if value is not UNSET:
                fields[key] = value
        if headers is not UNSET:
            fields["headers"], fields["secret_refs"] = split_headers(headers)
        await self._write(resource, _validated(fields), actor, description=description)
        return await self.view(name)

    async def delete_group(self, name: str, *, actor: str) -> None:
        resource, _ = await self.group(name)
        await self._resources.delete(resource.uid, actor=actor)
        await self._reach.delete_group(resource.uid)

    # --- tools -------------------------------------------------------------

    async def add_tool(self, name: str, raw: dict[str, Any], *, actor: str) -> GroupView:
        resource, transport = await self.group(name)
        tool = validated_tool(raw)
        if transport.tool(tool.name) is not None:
            raise CustomToolExists(name, tool.name)
        await self._write(
            resource, transport.model_copy(update={"tools": [*transport.tools, tool]}), actor
        )
        return await self.view(name)

    async def update_tool(
        self, name: str, tool_name: str, changes: dict[str, Any], *, actor: str
    ) -> GroupView:
        resource, transport = await self.group(name)
        current = transport.tool(tool_name)
        if current is None:
            raise CustomToolNotFound(name, tool_name)
        merged = validated_tool({**current.model_dump(mode="json"), **changes})
        if merged.name != tool_name and transport.tool(merged.name) is not None:
            raise CustomToolExists(name, merged.name)
        tools = [merged if t.name == tool_name else t for t in transport.tools]
        await self._write(resource, transport.model_copy(update={"tools": tools}), actor)
        if merged.name != tool_name:
            overrides = (await self._reach.overrides_for([resource.uid])).get(resource.uid, {})
            if tool_name in overrides:
                await self._reach.set_override(resource.uid, merged.name, overrides[tool_name])
            await self._reach.delete_tools(resource.uid, [tool_name])
        return await self.view(name)

    async def delete_tool(self, name: str, tool_name: str, *, actor: str) -> GroupView:
        resource, transport = await self.group(name)
        if transport.tool(tool_name) is None:
            raise CustomToolNotFound(name, tool_name)
        tools = [t for t in transport.tools if t.name != tool_name]
        await self._write(resource, transport.model_copy(update={"tools": tools}), actor)
        await self._reach.delete_tools(resource.uid, [tool_name])
        return await self.view(name)

    async def set_tool_reach(
        self, name: str, tool_name: str, reach: ToolReach | None, *, actor: str
    ) -> GroupView:
        """Set one tool's override — a list of agent uids, or ``"all"`` (every
        agent, later ones too) — or clear it (``None``: same as the group).
        Machine-local; audited as a scope change naming the tool."""
        resource, transport = await self.group(name)
        if transport.tool(tool_name) is None:
            raise CustomToolNotFound(name, tool_name)
        if isinstance(reach, list) and any(not isinstance(a, str) or not a for a in reach):
            raise ConfigValidationError("a reach override lists agent uids")
        await self._reach.set_override(resource.uid, tool_name, reach)
        await self._audit.record(
            AuditEventType.RESOURCE_SCOPE_UPDATED.value,
            resource=resource,
            actor=actor,
            details={
                "tool": tool_name,
                "scope": None if reach is None else {"agents": None if reach == "all" else reach},
            },
        )
        return await self.view(name)

    async def test_tool(
        self, name: str, raw_tool: dict[str, Any], arguments: dict[str, Any]
    ) -> ToolTestOutcome:
        """Run a draft tool once against the group's base URL and secret.

        Nothing is saved and nothing enters the invocation log (spec
        mcp-gateway "Manage custom tools through REST and the Custom tools page"); the
        secret goes through the same boundary as a call does.
        """
        resource, transport = await self.group(name)
        tool = validated_tool(raw_tool)
        config = MCPServerConfig(transport=transport)
        overlay = await self._resolver().materialize_async(
            dict(transport.secret_refs), mcp_destination(resource.uid, resource.name, config)
        )
        return await self._runner.run(transport, tool, arguments, overlay)

    async def test_unsaved(
        self,
        *,
        base_url: str,
        headers: list[dict[str, Any]],
        timeout_seconds: int,
        raw_tool: dict[str, Any],
        arguments: dict[str, Any],
    ) -> ToolTestOutcome:
        """Run a request of a group that is not saved yet (spec mcp-gateway
        "Test a custom tool request before its group is saved").

        The group has no approved secret binding, so no secret is sent; its
        base URL was typed into a form, so the runner checks it against the
        SSRF guard. Nothing is saved or logged.
        """
        # A secret header is left out: an unsaved group has no approved binding.
        plain, _ = split_headers(headers)
        transport = _validated(
            {
                "base_url": base_url,
                "headers": plain,
                "timeout_seconds": timeout_seconds,
                "tools": [],
                "secret_refs": {},
            }
        )
        return await self._runner.run_unsaved(transport, validated_tool(raw_tool), arguments)

    # --- the one write path ----------------------------------------------------

    async def _write(
        self,
        resource: Resource,
        transport: HttpApiTransport,
        actor: str,
        *,
        description: Any = UNSET,
    ) -> Resource:
        config = MCPServerConfig.model_validate(resource.config).model_copy(
            update={"transport": _validated(transport.model_dump(mode="json"))}
        )
        return await self._resources.update_config(
            resource.uid,
            config.model_dump(mode="json"),
            actor,
            description=resource.description if description is UNSET else description,
        )

    async def write_transport(
        self, resource: Resource, transport: HttpApiTransport, actor: str
    ) -> Resource:
        """For ``custom_tool_import``: the same write path."""
        return await self._write(resource, transport, actor)

    @property
    def reach(self) -> ToolReachRepoPort:
        return self._reach

    def now(self) -> datetime:
        return self._clock()


__all__ = ["UNSET", "CustomToolService", "secret_name_of", "split_headers", "validated_tool"]
