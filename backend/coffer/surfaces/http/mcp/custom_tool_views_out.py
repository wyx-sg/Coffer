"""Map the custom-tool read model onto its wire models."""

from __future__ import annotations

from coffer.application.mcp.custom_tool_handoff import failing_group_handoff
from coffer.application.mcp.custom_tool_views import GroupView, ToolView
from coffer.application.mcp.custom_tools import secret_name_of
from coffer.domain.mcp.namespace import prefix_tool
from coffer.domain.mcp.openapi_import import DraftOperation
from coffer.surfaces.http.handoff_schemas import HandoffOut
from coffer.surfaces.http.mcp.custom_tool_schemas import (
    CustomToolGroupOut,
    CustomToolHeaderOut,
    CustomToolIn,
    CustomToolOut,
    OpenApiOperationOut,
    OpenApiSourceOut,
    OpenApiSourceTextOut,
)
from coffer.surfaces.http.mcp.handoff_views import host_machine


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
        calls_24h=view.calls,
        failures_24h=view.failures,
    )


def group_out(view: GroupView) -> CustomToolGroupOut:
    r, t = view.resource, view.transport
    headers = [
        CustomToolHeaderOut(name=name, value=value, secret=None, secret_state="none")
        for name, value in t.headers.items()
    ] + [
        CustomToolHeaderOut(
            name=name,
            value=None,
            secret=secret_name_of(ref),
            scheme=t.auth_schemes.get(name),
            secret_state=view.header_states.get(name, "present"),
        )
        for name, ref in t.secret_refs.items()
    ]
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
        headers=headers,
        timeout_seconds=t.timeout_seconds,
        scope=r.scope.agents if r.scope is not None else None,
        source=source,
        health=view.health,
        health_reason=view.health_reason,
        secret_state=view.secret_state,
        pending_approvals=view.pending_approvals,
        pending_secrets=view.pending_secrets,
        calls_24h=view.calls,
        failures_24h=view.failures,
        last_call_at=view.last_call_at,
        handoff=(
            HandoffOut(
                prompt=failing_group_handoff(
                    group=r.name,
                    base_url=str(t.base_url),
                    status=view.last_call_status,
                    error=view.last_call_error,
                    machine=host_machine(),
                )
            )
            if view.health == "failing"
            else None
        ),
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
            source_text=t.source_text,
        ),
        source=(
            OpenApiSourceTextOut(
                start_line=op.source.start_line, end_line=op.source.end_line, text=op.source.text
            )
            if op.source
            else None
        ),
    )
