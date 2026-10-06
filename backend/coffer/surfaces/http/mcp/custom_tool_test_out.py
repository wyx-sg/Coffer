"""A custom tool test's outcome as the wire carries it, with its hand-off."""

from __future__ import annotations

from coffer.application.mcp.custom_tool_handoff import request_test_handoff
from coffer.application.mcp.custom_tool_ports import ToolTestOutcome
from coffer.surfaces.http.handoff_schemas import HandoffOut
from coffer.surfaces.http.mcp.custom_tool_schemas import CustomToolTestOut
from coffer.surfaces.http.mcp.handoff_views import host_machine


def test_out(
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
        environment=o.environment,
        response_headers=o.response_headers,
    )


__all__ = ["test_out"]
