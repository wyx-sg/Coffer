"""Map the custom-tool read model onto its wire models."""

from __future__ import annotations

from coffer.application.mcp.custom_tool_views import GroupView, ToolView
from coffer.application.mcp.custom_tools import secret_name_of
from coffer.domain.mcp.namespace import prefix_tool
from coffer.domain.mcp.openapi_import import DraftOperation
from coffer.surfaces.http.mcp.custom_tool_schemas import (
    CustomToolAuthOut,
    CustomToolGroupOut,
    CustomToolIn,
    CustomToolOut,
    OpenApiOperationOut,
    OpenApiSourceOut,
)


def tool_out(group: str, view: ToolView) -> CustomToolOut:
    t = view.tool
    return CustomToolOut(
        name=t.name,
        agent_name=prefix_tool(group, t.name),
        description=t.description,
        method=t.method,
        path=t.path,
        headers=t.headers,
        body_template=t.body_template,
        input_schema=t.input_schema,
        enabled=t.enabled,
        changes_data=t.effective_changes_data,
        changes_data_set=t.changes_data is not None,
        operation=t.operation,
        reach_override=view.reach_override,
        calls_24h=view.calls,
        failures_24h=view.failures,
    )


def group_out(view: GroupView) -> CustomToolGroupOut:
    r, t = view.resource, view.transport
    auth = (
        CustomToolAuthOut(
            header=t.auth_header,
            prefix=t.auth_prefix,
            secret=secret_name_of(t),
            secret_state=view.secret_state,
        )
        if t.auth_header
        else None
    )
    source = (
        OpenApiSourceOut(
            kind=t.source.kind,
            location=t.source.location,
            title=t.source.title,
            version=t.source.version,
            fetched_at=t.source.fetched_at,
            skipped=t.source.skipped,
        )
        if t.source
        else None
    )
    return CustomToolGroupOut(
        uid=r.uid,
        name=r.name,
        description=r.description,
        enabled=r.enabled,
        base_url=str(t.base_url),
        headers=t.headers,
        auth=auth,
        timeout_seconds=t.timeout_seconds,
        scope=r.scope.agents if r.scope is not None else None,
        source=source,
        health=view.health,
        health_reason=view.health_reason,
        secret_state=view.secret_state,
        pending_approvals=view.pending_approvals,
        calls_24h=view.calls,
        failures_24h=view.failures,
        last_call_at=view.last_call_at,
        tools=[tool_out(r.name, tv) for tv in view.tools],
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


def operation_out(op: DraftOperation) -> OpenApiOperationOut:
    t = op.tool
    return OpenApiOperationOut(
        key=op.key,
        summary=op.summary,
        tag=op.tag,
        tool=CustomToolIn(
            name=t.name,
            description=t.description,
            method=t.method,
            path=t.path,
            headers=t.headers,
            body_template=t.body_template,
            input_schema=t.input_schema,
            enabled=t.enabled,
            changes_data=t.changes_data,
            operation=t.operation,
        ),
    )
