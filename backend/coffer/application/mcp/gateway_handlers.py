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
from mcp import MCPError

from coffer.application.mcp.invocation_outcome import (
    INBAND_TOOL_ERROR,
    answered_rpc_error,
)
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
from coffer.domain.scope import is_active

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
    those into the invocation log, defeating the rule that no secret value
    appears in any invocation record (spec credentials "Hold plaintext only in
    memory at the moment of use").

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

    A well-formed ``MCPError`` is a protocol-level JSON-RPC error: the request
    reached the upstream, the tool ran, and it returned an error result. The
    connection is healthy — evicting it would kill+respawn a perfectly good
    server on every tool that returns an error.

    The one exception is the SDK's ``CONNECTION_CLOSED`` (-32000) MCPError: the
    SDK raises that when the transport itself died mid-request (a crashed
    subprocess, a dropped pipe), so despite being an MCPError it IS a transport
    failure and must self-heal. Everything that is not an MCPError (a raw pipe
    error, a dead-process exception) is likewise a transport failure.
    """
    if isinstance(e, MCPError):
        return e.code == mcp_types.CONNECTION_CLOSED
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
    resource_uid: str,
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
            resource_uid=resource_uid,
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
    # tools/call results carry an in-band ``isError`` flag (per the MCP spec): a
    # tool that fails returns a well-formed result with ``isError: True`` rather
    # than raising. resources/read and prompts/get have no such flag. Only the
    # tool spec inspects the coerced result to record an honest ``error`` status.
    detects_inband_error: bool = False


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
    session_agent_uid: str | None = None,
) -> Any:
    prefixed = params.get(spec.param_key, "")
    try:
        server_name, original = spec.parse(prefixed)
    except InvalidPrefix as e:
        raise ToolDisabled(f"unrecognised {spec.label}: {prefixed!r}") from e

    # A LABEL is resolved here because a label is genuinely all the caller gave
    # us: what arrived is a namespaced wire key the downstream client composed
    # from the server's name (``<server>__<tool>``), which is the one vocabulary
    # that side of the wire has. From the resolved row onward everything
    # PERSISTED or COMPARED uses the identity — ``resource.uid`` for the
    # invocation log, ``resource.scope`` for the reach gate, ``resource.id`` for
    # the preference rows. The name survives only as the key of this session's
    # live connection (``supervisor``/``ensure_subscribed``), which is
    # in-process, rebuilt per session, and deliberately the same key the client
    # addressed.
    resource = await resources.get_by_name("mcp_server", server_name)

    async def _record(
        status: Literal["ok", "error", "timeout", "denied"],
        error_message: str | None = None,
        duration_ms: int = 0,
    ) -> None:
        await record_invocation(
            invocations,
            session_id=session_id,
            clock=clock,
            resource_uid=resource.uid,
            capability_type=spec.capability_type,
            capability_key=original,
            duration_ms=duration_ms,
            status=status,
            error_message=error_message,
        )

    # A disabled server is refused here, per call, and not only hidden from the
    # listings (gateway_scope): a session that listed the server before it was
    # disabled still holds its namespaced names, and nothing else on this path
    # would stop it — the supervisor hands back a cached healthy connection
    # without reading the flag. Same shape as a disabled capability: a
    # ``denied`` row and ToolDisabled (spec mcp-gateway "Toggle individual
    # capabilities"), since to the caller the whole server's capabilities are
    # now disabled ones.
    if not resource.enabled:
        await _record("denied")
        raise ToolDisabled(f"{server_name!r} is disabled")

    # Activation scope (see "Gate server exposure by scope per session"): tools/list
    # already hides a server this session's scope excludes
    # (gateway._enabled_mcp_servers), but that is only a listing-side filter — nothing
    # on the call-routing path re-checked it, so a caller that already knows (or
    # guesses) a hidden server's namespaced tool name could invoke it directly. The
    # supervisor's spawn gate has no session context, so this check lives here, at the
    # session's invocation seam, where the session's agent uid is known. Both sides of
    # the comparison are uids: ``scope.agents`` holds agent uids and the shim reports
    # one, so there is nothing to translate and no label that can go stale under a
    # rename.
    if not is_active(resource.scope, session_agent_uid):
        await _record("denied")
        # Same "indistinguishable from a disabled capability" shape "Gate server
        # exposure by scope per session" specifies for a hidden server: ToolDisabled,
        # not UpstreamUnavailable (that stays reserved for an upstream that genuinely
        # won't start).
        raise ToolDisabled(f"{server_name!r} is not in scope here")

    try:
        await check_capability_enabled(prefs, resource.id, spec.capability_type, original)
    except ToolDisabled:
        await _record("denied")
        raise

    # The clock starts BEFORE the upstream is obtained, and obtaining it sits
    # inside the recorded block: a call that fails because the upstream would
    # not start (cooldown, an exhausted spawn ladder) is still a call, and spec
    # mcp-gateway "Record invocations without content" wants an entry for every
    # one — and "Route calls to the originating upstream" wants that failure
    # visible in the log.
    started = clock()
    status: Literal["ok", "error", "timeout", "denied"] = "ok"
    error_msg: str | None = None
    requested = False
    try:
        conn = await supervisor.get_or_spawn(server_name)
        await ensure_subscribed(server_name)
        requested = True
        result = await conn.request(spec.method, spec.build_request(original, params))
        coerced = spec.coerce(result)
        # An in-band tool error (CallToolResult.isError) does not raise — the
        # connection is healthy, but the tool failed. Record an honest `error`
        # status so the invocation log distinguishes success from failure. The
        # error text is upstream-controlled (may echo secrets), so persist only
        # a fixed Coffer-authored marker, never the result content (spec
        # mcp-gateway "Record invocations without content"). The marker is also
        # how the status route tells "the tool failed" from "the server is down"
        # (invocation_outcome).
        if spec.detects_inband_error and isinstance(coerced, dict) and coerced.get("isError"):
            status = "error"
            error_msg = INBAND_TOOL_ERROR
        return coerced
    except UpstreamTimeout as e:
        status = "timeout"
        error_msg = _safe_error_summary(e)
        raise
    except Exception as e:
        status = "error"
        # Only self-heal on a transport/process failure. A well-formed MCPError
        # means the tool ran and returned an error result over a healthy
        # connection — evicting it would needlessly kill+respawn a good server.
        # And only once a request was actually sent: a failure to OBTAIN the
        # connection has no connection to evict.
        if isinstance(e, MCPError) and not _is_transport_failure(e):
            error_msg = answered_rpc_error(e.code)
        else:
            error_msg = _safe_error_summary(e)
            if requested:
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
        await _record(status, error_msg, duration_ms)


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
    which silently masked SDK contract drift. ``method`` only
    flavours the error message.

    A single implementation behind the three thin wrappers below,
    which used to be byte-identical except for that message.
    """
    if hasattr(sdk_result, "model_dump"):
        dumped: dict[str, Any] = sdk_result.model_dump(
            exclude_none=True, mode="json", by_alias=True
        )
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
    detects_inband_error=True,
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
