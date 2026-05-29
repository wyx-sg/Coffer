"""Invocation handlers for MCPGatewaySession (tools/call, resources/read, prompts/get).

Extracted from gateway.py to keep that module under 400 LOC.
These functions are called by MCPGatewaySession methods and require
the session's state — they are intentionally module-level to avoid
deep nesting while keeping gateway.py readable.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

from coffer.application.mcp.ports import (
    MCPCapabilityPreferenceRepoPort,
    MCPInvocationRepoPort,
)
from coffer.domain.errors import (
    CofferError,
    InvalidPrefix,
    ToolDisabled,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from coffer.domain.mcp.capability import CapabilityType, MCPInvocation
from coffer.domain.mcp.namespace import (
    parse_prefixed_prompt,
    parse_prefixed_tool,
    parse_prefixed_uri,
)
from coffer.domain.resource import ResourceRef

if TYPE_CHECKING:
    from coffer.application.mcp.supervisor import SubprocessSupervisor
    from coffer.application.resource_service import ResourceService


# --------------------------------------------------------------------------- #
# Preference + invocation helpers                                              #
# --------------------------------------------------------------------------- #


def _safe_error_summary(e: BaseException) -> str:
    """Build an invocation-log-safe error summary.

    Why: upstream MCP servers can include user-controlled or secret content
    inside their error messages (e.g., an auth failure that echoes the API
    key back). Persisting ``str(e)`` for arbitrary exceptions would leak
    those into the invocation log, defeating SC-010.

    Rule: for Coffer-internal exceptions (CofferError subclasses) the message
    is authored by Coffer and safe to keep. For everything else, store only
    the class name.
    """
    if isinstance(e, CofferError):
        return f"{type(e).__name__}: {e}"
    return type(e).__name__


async def check_capability_enabled(
    prefs: MCPCapabilityPreferenceRepoPort,
    resource_id: int,
    capability_type: CapabilityType,
    capability_key: str,
) -> None:
    """Raise ToolDisabled if the preference row exists and is disabled."""
    pref = await prefs.find(resource_id, capability_type, capability_key)
    # Missing row → default to enabled (matches CapabilityDiscovery's behaviour).
    if pref is not None and not pref.enabled:
        raise ToolDisabled(f"{capability_type}:{capability_key!r} is disabled on this server")


async def record_invocation(
    invocations: MCPInvocationRepoPort,
    *,
    session_id: str,
    clock: Callable[[], datetime],
    resource_name: str,
    capability_type: CapabilityType,
    capability_key: str,
    duration_ms: int,
    status: Literal["ok", "error", "timeout", "denied"],
    error_message: str | None,
) -> None:
    await invocations.insert(
        MCPInvocation(
            id=None,
            timestamp=clock(),
            resource_name=resource_name,
            capability_type=capability_type,
            capability_key=capability_key,
            duration_ms=duration_ms,
            status=status,
            error_message=error_message,
            session_id=session_id,
        )
    )


# --------------------------------------------------------------------------- #
# Invocation handlers                                                          #
# --------------------------------------------------------------------------- #


async def handle_tools_call(
    params: dict[str, Any],
    *,
    resources: ResourceService,
    supervisor: SubprocessSupervisor,
    prefs: MCPCapabilityPreferenceRepoPort,
    invocations: MCPInvocationRepoPort,
    session_id: str,
    clock: Callable[[], datetime],
    ensure_subscribed: Callable[[str], Any],
    on_evict: Callable[[str], None] | None = None,
) -> Any:
    prefixed = params.get("name", "")
    try:
        server_name, original_name = parse_prefixed_tool(prefixed)
    except InvalidPrefix as e:
        raise ToolDisabled(f"unrecognised tool name: {prefixed!r}") from e

    resource = await resources.get(ResourceRef("mcp_server", server_name))
    try:
        await check_capability_enabled(prefs, resource.id, "tool", original_name)
    except ToolDisabled:
        await record_invocation(
            invocations,
            session_id=session_id,
            clock=clock,
            resource_name=server_name,
            capability_type="tool",
            capability_key=original_name,
            duration_ms=0,
            status="denied",
            error_message=None,
        )
        raise

    conn = await supervisor.get_or_spawn(server_name)
    await ensure_subscribed(server_name)

    started = clock()
    status: Literal["ok", "error", "timeout", "denied"] = "ok"
    error_msg: str | None = None
    try:
        result = await conn.request(
            "tools/call",
            {"name": original_name, "arguments": params.get("arguments", {})},
        )
        return coerce_call_result(result)
    except UpstreamTimeout as e:
        status = "timeout"
        error_msg = _safe_error_summary(e)
        raise
    except Exception as e:
        status = "error"
        error_msg = _safe_error_summary(e)
        # Evict the broken connection so the next call triggers a respawn.
        await supervisor.evict(server_name)
        # Discard the subscription so _ensure_subscribed re-registers the
        # callback on the fresh connection spawned by the next call.
        if on_evict is not None:
            with contextlib.suppress(Exception):
                on_evict(server_name)
        raise
    finally:
        duration_ms = int((clock() - started).total_seconds() * 1000)
        await record_invocation(
            invocations,
            session_id=session_id,
            clock=clock,
            resource_name=server_name,
            capability_type="tool",
            capability_key=original_name,
            duration_ms=duration_ms,
            status=status,
            error_message=error_msg,
        )


async def handle_resources_read(
    params: dict[str, Any],
    *,
    resources: ResourceService,
    supervisor: SubprocessSupervisor,
    prefs: MCPCapabilityPreferenceRepoPort,
    invocations: MCPInvocationRepoPort,
    session_id: str,
    clock: Callable[[], datetime],
    ensure_subscribed: Callable[[str], Any],
    on_evict: Callable[[str], None] | None = None,
) -> Any:
    prefixed = params.get("uri", "")
    try:
        server_name, original_uri = parse_prefixed_uri(prefixed)
    except InvalidPrefix as e:
        raise ToolDisabled(f"unrecognised resource uri: {prefixed!r}") from e

    resource = await resources.get(ResourceRef("mcp_server", server_name))
    try:
        await check_capability_enabled(prefs, resource.id, "resource", original_uri)
    except ToolDisabled:
        await record_invocation(
            invocations,
            session_id=session_id,
            clock=clock,
            resource_name=server_name,
            capability_type="resource",
            capability_key=original_uri,
            duration_ms=0,
            status="denied",
            error_message=None,
        )
        raise

    conn = await supervisor.get_or_spawn(server_name)
    await ensure_subscribed(server_name)

    started = clock()
    status: Literal["ok", "error", "timeout", "denied"] = "ok"
    error_msg: str | None = None
    try:
        result = await conn.request("resources/read", {"uri": original_uri})
        return coerce_read_result(result)
    except UpstreamTimeout as e:
        status = "timeout"
        error_msg = _safe_error_summary(e)
        raise
    except Exception as e:
        status = "error"
        error_msg = _safe_error_summary(e)
        # Evict the broken connection so the next call triggers a respawn.
        await supervisor.evict(server_name)
        # Discard the subscription so _ensure_subscribed re-registers the
        # callback on the fresh connection spawned by the next call.
        if on_evict is not None:
            with contextlib.suppress(Exception):
                on_evict(server_name)
        raise
    finally:
        duration_ms = int((clock() - started).total_seconds() * 1000)
        await record_invocation(
            invocations,
            session_id=session_id,
            clock=clock,
            resource_name=server_name,
            capability_type="resource",
            capability_key=original_uri,
            duration_ms=duration_ms,
            status=status,
            error_message=error_msg,
        )


async def handle_prompts_get(
    params: dict[str, Any],
    *,
    resources: ResourceService,
    supervisor: SubprocessSupervisor,
    prefs: MCPCapabilityPreferenceRepoPort,
    invocations: MCPInvocationRepoPort,
    session_id: str,
    clock: Callable[[], datetime],
    ensure_subscribed: Callable[[str], Any],
    on_evict: Callable[[str], None] | None = None,
) -> Any:
    prefixed = params.get("name", "")
    try:
        server_name, original_name = parse_prefixed_prompt(prefixed)
    except InvalidPrefix as e:
        raise ToolDisabled(f"unrecognised prompt name: {prefixed!r}") from e

    resource = await resources.get(ResourceRef("mcp_server", server_name))
    try:
        await check_capability_enabled(prefs, resource.id, "prompt", original_name)
    except ToolDisabled:
        await record_invocation(
            invocations,
            session_id=session_id,
            clock=clock,
            resource_name=server_name,
            capability_type="prompt",
            capability_key=original_name,
            duration_ms=0,
            status="denied",
            error_message=None,
        )
        raise

    conn = await supervisor.get_or_spawn(server_name)
    await ensure_subscribed(server_name)

    started = clock()
    status: Literal["ok", "error", "timeout", "denied"] = "ok"
    error_msg: str | None = None
    try:
        result = await conn.request(
            "prompts/get",
            {"name": original_name, "arguments": params.get("arguments")},
        )
        return coerce_prompt_result(result)
    except UpstreamTimeout as e:
        status = "timeout"
        error_msg = _safe_error_summary(e)
        raise
    except Exception as e:
        status = "error"
        error_msg = _safe_error_summary(e)
        # Evict the broken connection so the next call triggers a respawn.
        await supervisor.evict(server_name)
        # Discard the subscription so _ensure_subscribed re-registers the
        # callback on the fresh connection spawned by the next call.
        if on_evict is not None:
            with contextlib.suppress(Exception):
                on_evict(server_name)
        raise
    finally:
        duration_ms = int((clock() - started).total_seconds() * 1000)
        await record_invocation(
            invocations,
            session_id=session_id,
            clock=clock,
            resource_name=server_name,
            capability_type="prompt",
            capability_key=original_name,
            duration_ms=duration_ms,
            status=status,
            error_message=error_msg,
        )


# --------------------------------------------------------------------------- #
# SDK result coercion                                                           #
# --------------------------------------------------------------------------- #


def coerce_call_result(sdk_result: Any) -> dict[str, Any]:
    """Convert mcp SDK CallToolResult to a JSON-friendly dict.

    Raises UpstreamUnavailable when the result is neither a Pydantic model
    nor a dict — previously this returned ``{"content": []}`` which silently
    masked SDK contract drift (CODE-009).
    """
    if hasattr(sdk_result, "model_dump"):
        dumped: dict[str, Any] = sdk_result.model_dump(exclude_none=True, mode="json")
        return dumped
    if isinstance(sdk_result, dict):
        return sdk_result
    raise UpstreamUnavailable("upstream returned unparseable tools/call result")


def coerce_read_result(sdk_result: Any) -> dict[str, Any]:
    if hasattr(sdk_result, "model_dump"):
        dumped: dict[str, Any] = sdk_result.model_dump(exclude_none=True, mode="json")
        return dumped
    if isinstance(sdk_result, dict):
        return sdk_result
    raise UpstreamUnavailable("upstream returned unparseable resources/read result")


def coerce_prompt_result(sdk_result: Any) -> dict[str, Any]:
    if hasattr(sdk_result, "model_dump"):
        dumped: dict[str, Any] = sdk_result.model_dump(exclude_none=True, mode="json")
        return dumped
    if isinstance(sdk_result, dict):
        return sdk_result
    raise UpstreamUnavailable("upstream returned unparseable prompts/get result")
