"""``/api/v1/custom-tools`` — custom-tool groups and their tools.

Spec mcp-gateway "Manage custom tools through REST and the Custom tools page"; design
add-http-custom-tools §9. A group is addressed by its fixed name, like an MCP
server on the page that shows it. Enabling, disabling and the group's reach use
the kind-agnostic resource routes by the group's uid.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Response

from coffer.application.mcp.custom_tool_handoff import request_test_handoff
from coffer.application.mcp.custom_tool_import import CustomToolImporter
from coffer.application.mcp.custom_tool_ports import ToolTestOutcome
from coffer.application.mcp.custom_tools import UNSET, CustomToolService
from coffer.domain.errors import ConfigValidationError
from coffer.surfaces.http.auth import require_token
from coffer.surfaces.http.dependencies import get_actor
from coffer.surfaces.http.handoff_schemas import HandoffOut
from coffer.surfaces.http.mcp.custom_tool_dependencies import (
    get_custom_tool_importer,
    get_custom_tool_service,
)
from coffer.surfaces.http.mcp.custom_tool_schemas import (
    CustomToolGroupIn,
    CustomToolGroupListOut,
    CustomToolGroupOut,
    CustomToolGroupPatch,
    CustomToolHeaderIn,
    CustomToolIn,
    CustomToolPatch,
    CustomToolReimportChangeOut,
    CustomToolReimportIn,
    CustomToolReimportPreviewOut,
    CustomToolTestIn,
    CustomToolTestOut,
    CustomToolUnsavedTestIn,
    OpenApiReadIn,
    OpenApiReadOut,
)
from coffer.surfaces.http.mcp.custom_tool_views_out import group_out, operation_out
from coffer.surfaces.http.mcp.handoff_views import host_machine

router = APIRouter(
    prefix="/api/v1/custom-tools",
    tags=["custom-tools"],
    dependencies=[Depends(require_token)],
)

_service = Depends(get_custom_tool_service)
_importer = Depends(get_custom_tool_importer)
_actor = Depends(get_actor)


def _header_rows(rows: list[CustomToolHeaderIn]) -> list[dict[str, Any]]:
    return [r.model_dump() for r in rows]


def _tool_dict(tool: CustomToolIn) -> dict[str, object]:
    return tool.model_dump(mode="json")


@router.get("", response_model=CustomToolGroupListOut)
async def list_groups(svc: CustomToolService = _service) -> CustomToolGroupListOut:
    return CustomToolGroupListOut(groups=[group_out(v) for v in await svc.list_groups()])


@router.post("", response_model=CustomToolGroupOut, status_code=201)
async def create_group(
    body: CustomToolGroupIn, svc: CustomToolService = _service, actor: str = _actor
) -> CustomToolGroupOut:
    source = (
        {**body.source.model_dump(mode="json"), "fetched_at": datetime.now(tz=UTC).isoformat()}
        if body.source
        else None
    )
    view = await svc.create_group(
        name=body.name,
        description=body.description,
        base_url=body.base_url,
        headers=_header_rows(body.headers),
        timeout_seconds=body.timeout_seconds,
        agents=body.agents,
        tools=[_tool_dict(t) for t in body.tools],
        source=source,
        actor=actor,
    )
    return group_out(view)


@router.post("/openapi", response_model=OpenApiReadOut)
async def read_openapi(
    body: OpenApiReadIn, importer: CustomToolImporter = _importer
) -> OpenApiReadOut:
    """Read a document into draft tools; saves nothing."""
    result = await importer.read(url=body.url, document=body.document, filename=body.filename)
    r = result.reading
    return OpenApiReadOut(
        title=r.title,
        version=r.version,
        base_url=r.base_url,
        auth_header=r.auth_header,
        source_kind=result.kind,
        location=result.location,
        operations=[operation_out(op) for op in r.operations],
        warnings=r.warnings,
    )


@router.post("/test", response_model=CustomToolTestOut)
async def test_unsaved(
    body: CustomToolUnsavedTestIn, svc: CustomToolService = _service
) -> CustomToolTestOut:
    """Run a request of a group not saved yet: no secret, SSRF-guarded, nothing kept."""
    o = await svc.test_unsaved(
        base_url=body.base_url,
        headers=_header_rows(body.headers),
        timeout_seconds=body.timeout_seconds,
        raw_tool=_tool_dict(body.tool),
        arguments=body.arguments,
    )
    return _test_out(o, group=None, method=body.tool.method, seconds=body.timeout_seconds)


@router.get("/{name}", response_model=CustomToolGroupOut)
async def get_group(name: str, svc: CustomToolService = _service) -> CustomToolGroupOut:
    return group_out(await svc.view(name))


@router.patch("/{name}", response_model=CustomToolGroupOut)
async def update_group(
    name: str,
    body: CustomToolGroupPatch,
    svc: CustomToolService = _service,
    actor: str = _actor,
) -> CustomToolGroupOut:
    sent = body.model_fields_set
    kwargs: dict[str, object] = {}
    for field in ("description", "base_url", "timeout_seconds"):
        if field in sent:
            value = getattr(body, field)
            if value is None and field != "description":
                raise ConfigValidationError(f"{field} cannot be cleared")
            kwargs[field] = value
    if "headers" in sent:
        if body.headers is None:
            raise ConfigValidationError("headers cannot be cleared")
        kwargs["headers"] = _header_rows(body.headers)
    view = await svc.update_group(name, actor=actor, **{k: kwargs.get(k, UNSET) for k in kwargs})
    return group_out(view)


@router.delete("/{name}", status_code=204, response_class=Response)
async def delete_group(
    name: str, svc: CustomToolService = _service, actor: str = _actor
) -> Response:
    await svc.delete_group(name, actor=actor)
    return Response(status_code=204)


@router.post("/{name}/tools", response_model=CustomToolGroupOut, status_code=201)
async def add_tool(
    name: str, body: CustomToolIn, svc: CustomToolService = _service, actor: str = _actor
) -> CustomToolGroupOut:
    return group_out(await svc.add_tool(name, _tool_dict(body), actor=actor))


@router.patch("/{name}/tools/{tool}", response_model=CustomToolGroupOut)
async def update_tool(
    name: str,
    tool: str,
    body: CustomToolPatch,
    svc: CustomToolService = _service,
    actor: str = _actor,
) -> CustomToolGroupOut:
    changes = body.model_dump(mode="json", exclude_unset=True)
    for field in ("name", "method", "path", "headers", "input_schema", "enabled", "description"):
        if field in changes and changes[field] is None:
            raise ConfigValidationError(f"{field} cannot be cleared")
    return group_out(await svc.update_tool(name, tool, changes, actor=actor))


@router.delete("/{name}/tools/{tool}", response_model=CustomToolGroupOut)
async def delete_tool(
    name: str, tool: str, svc: CustomToolService = _service, actor: str = _actor
) -> CustomToolGroupOut:
    return group_out(await svc.delete_tool(name, tool, actor=actor))


@router.post("/{name}/test", response_model=CustomToolTestOut)
async def test_tool(
    name: str, body: CustomToolTestIn, svc: CustomToolService = _service
) -> CustomToolTestOut:
    """Run a draft tool once; saves nothing and records no invocation."""
    outcome = await svc.test_tool(name, _tool_dict(body.tool), body.arguments)
    return _test_out(outcome, group=name, method=body.tool.method)


def _test_out(
    o: ToolTestOutcome, *, group: str | None, method: str, seconds: int | None = None
) -> CustomToolTestOut:
    handoff = (
        HandoffOut(
            prompt=request_test_handoff(
                group=group,
                method=method,
                url=o.url,
                failure=o.failure,
                error=o.error,
                seconds=seconds,
                machine=host_machine(),
            )
        )
        if o.failure in ("connect", "timeout")
        else None
    )
    return CustomToolTestOut(
        ok=o.ok,
        duration_ms=o.duration_ms,
        url=o.url,
        status=o.status,
        status_line=o.status_line,
        body=o.body,
        truncated=o.truncated,
        content_type=o.content_type,
        error=o.error,
        failure=o.failure,  # type: ignore[arg-type]
        handoff=handoff,
    )


@router.post("/{name}/reimport/preview", response_model=CustomToolReimportPreviewOut)
async def preview_reimport(
    name: str, body: CustomToolReimportIn, importer: CustomToolImporter = _importer
) -> CustomToolReimportPreviewOut:
    reading, plan, changes = await importer.preview(name, document=body.document)
    return CustomToolReimportPreviewOut(
        title=reading.title,
        version=reading.version,
        added=[operation_out(op) for op in plan.added],
        removed=plan.removed,
        kept=plan.kept,
        changed=[
            CustomToolReimportChangeOut(
                name=c.name,
                method=c.method,  # type: ignore[arg-type]
                path=c.path,
                new_required=c.new_required,
                request_changed=c.request_changed,
                operation=c.operation,
                old_text=c.old_text,
                new_text=c.new_text,
                new_start_line=c.new_start_line,
                new_end_line=c.new_end_line,
            )
            for c in changes
        ],
        warnings=reading.warnings,
    )


@router.post("/{name}/reimport", response_model=CustomToolGroupOut)
async def apply_reimport(
    name: str,
    body: CustomToolReimportIn,
    importer: CustomToolImporter = _importer,
    actor: str = _actor,
) -> CustomToolGroupOut:
    view = await importer.apply(name, document=body.document, add_keys=set(body.add), actor=actor)
    return group_out(view)
