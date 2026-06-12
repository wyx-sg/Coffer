"""Invocation handlers for MCPGatewaySession (tools/call, resources/read, prompts/get).

Extracted from gateway.py to keep that module under 400 LOC.
These functions are called by MCPGatewaySession methods and require
the session's state — they are intentionally module-level to avoid
deep nesting while keeping gateway.py readable.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

import mcp.types as mcp_types
from mcp import McpError

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


def _is_transport_failure(e: BaseException) -> bool:
    """True when an upstream request failure should self-heal by evicting the
    connection (transport/process death), False when the upstream answered.

    A well-formed ``McpError`` is a protocol-level JSON-RPC error: the request
    reached the upstream, the tool ran, and it returned an error result. The
    connection is healthy — evicting it would kill+respawn a perfectly good
    server on every tool that returns an error.

    The one exception is the SDK's ``CONNECTION_CLOSED`` (-32000) McpError: the
    SDK raises that when the transport itself died mid-request (a crashed
    subprocess, a dropped pipe), so despite being an McpError it IS a transport
    failure and must self-heal. Everything that is not an McpError (a raw pipe
    error, a dead-process exception) is likewise a transport failure.
    """
    if isinstance(e, McpError):
        return e.error.code == mcp_types.CONNECTION_CLOSED
    return True


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


@dataclass(frozen=True)
class _CapabilitySpec:
    """Per-capability-kind knobs that drive the shared invocation pipeline.

    The three public handlers below differ ONLY in these fields; the
    parse → capability-gate → spawn → request → evict-on-error →
    record-invocation flow is identical and lives once in ``_invoke``.
    """

    capability_type: CapabilityType
    param_key: str  # where the prefixed key lives in params: "name" / "uri"
    label: str  # used in the "unrecognised <label>" denial message
    parse: Callable[[str], tuple[str, str]]  # prefixed -> (server, original)
    method: str  # upstream JSON-RPC method
    build_request: Callable[[str, dict[str, Any]], dict[str, Any]]  # (orig, params) -> req
    coerce: Callable[[Any], dict[str, Any]]


async def _invoke(
    params: dict[str, Any],
    spec: _CapabilitySpec,
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
    prefixed = params.get(spec.param_key, "")
    try:
        server_name, original = spec.parse(prefixed)
    except InvalidPrefix as e:
        raise ToolDisabled(f"unrecognised {spec.label}: {prefixed!r}") from e

    resource = await resources.get(ResourceRef("mcp_server", server_name))
    try:
        await check_capability_enabled(prefs, resource.id, spec.capability_type, original)
    except ToolDisabled:
        await record_invocation(
            invocations,
            session_id=session_id,
            clock=clock,
            resource_name=server_name,
            capability_type=spec.capability_type,
            capability_key=original,
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
        result = await conn.request(spec.method, spec.build_request(original, params))
        return spec.coerce(result)
    except UpstreamTimeout as e:
        status = "timeout"
        error_msg = _safe_error_summary(e)
        raise
    except Exception as e:
        status = "error"
        error_msg = _safe_error_summary(e)
        # Only self-heal on a transport/process failure. A well-formed McpError
        # means the tool ran and returned an error result over a healthy
        # connection — evicting it would needlessly kill+respawn a good server.
        if _is_transport_failure(e):
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
            capability_type=spec.capability_type,
            capability_key=original,
            duration_ms=duration_ms,
            status=status,
            error_message=error_msg,
        )


async def handle_tools_call(params: dict[str, Any], **kw: Any) -> Any:
    return await _invoke(params, _TOOL_SPEC, **kw)


async def handle_resources_read(params: dict[str, Any], **kw: Any) -> Any:
    return await _invoke(params, _RESOURCE_SPEC, **kw)


async def handle_prompts_get(params: dict[str, Any], **kw: Any) -> Any:
    return await _invoke(params, _PROMPT_SPEC, **kw)


# --------------------------------------------------------------------------- #
# SDK result coercion                                                           #
# --------------------------------------------------------------------------- #


def _coerce_result(sdk_result: Any, method: str) -> dict[str, Any]:
    """Convert an mcp SDK result object to a JSON-friendly dict.

    Raises UpstreamUnavailable when the result is neither a Pydantic model
    nor a dict — previously the tools/call path returned ``{"content": []}``
    which silently masked SDK contract drift (CODE-009). ``method`` only
    flavours the error message.

    CODE-040: single implementation behind the three thin wrappers below,
    which used to be byte-identical except for that message.
    """
    if hasattr(sdk_result, "model_dump"):
        dumped: dict[str, Any] = sdk_result.model_dump(exclude_none=True, mode="json")
        return dumped
    if isinstance(sdk_result, dict):
        return sdk_result
    raise UpstreamUnavailable(f"upstream returned unparseable {method} result")


def coerce_call_result(sdk_result: Any) -> dict[str, Any]:
    return _coerce_result(sdk_result, "tools/call")


def coerce_read_result(sdk_result: Any) -> dict[str, Any]:
    return _coerce_result(sdk_result, "resources/read")


def coerce_prompt_result(sdk_result: Any) -> dict[str, Any]:
    return _coerce_result(sdk_result, "prompts/get")


# --------------------------------------------------------------------------- #
# Capability specs (defined after coerce_* so they can reference them)         #
# --------------------------------------------------------------------------- #

_TOOL_SPEC = _CapabilitySpec(
    capability_type="tool",
    param_key="name",
    label="tool name",
    parse=parse_prefixed_tool,
    method="tools/call",
    build_request=lambda original, params: {
        "name": original,
        "arguments": params.get("arguments", {}),
    },
    coerce=coerce_call_result,
)

_RESOURCE_SPEC = _CapabilitySpec(
    capability_type="resource",
    param_key="uri",
    label="resource uri",
    parse=parse_prefixed_uri,
    method="resources/read",
    build_request=lambda original, _params: {"uri": original},
    coerce=coerce_read_result,
)

_PROMPT_SPEC = _CapabilitySpec(
    capability_type="prompt",
    param_key="name",
    label="prompt name",
    parse=parse_prefixed_prompt,
    method="prompts/get",
    build_request=lambda original, params: {
        "name": original,
        "arguments": params.get("arguments"),
    },
    coerce=coerce_prompt_result,
)
