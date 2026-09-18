"""The seam a workflow run's tool call can be held at (spec workflow FR-034).

The gateway does not know what a workflow is, and the import fence in
``backend/pyproject.toml`` keeps it that way: ``application.mcp`` may not import
``application.workflow``. So the hold is expressed here as a Protocol the
composition root fills with the workflow's gate, plus the one guard that decides
whether to consult it at all.

That guard is the whole of the "an ordinary conversation is untouched"
guarantee, and it is deliberately two plain ``is not None`` checks rather than a
null-object or a default gate. With nothing wired, or with no run identity on
the session, the port is never awaited and the call reaches
``handle_tools_call`` with the same arguments it would have reached before this
module existed — which is the property the removal ADR
(``docs/decisions/remove-tool-approval.md``) is owed: every conversation a
person is driving behaves exactly as it did.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from coffer.application.mcp.gateway_handlers import handle_tools_call

#: ``MCPGatewaySession._dispatch_handler`` — (handler, params) -> result.
UpstreamDispatch = Callable[[Callable[..., Awaitable[Any]], dict[str, Any]], Awaitable[Any]]


class ToolCallGatePort(Protocol):
    """What the gateway asks before dispatching an upstream tool call.

    ``None`` means dispatch. A dict is a ``tools/call`` result the gateway
    returns downstream *instead of* dispatching — an ``isError`` result whose
    text says why, so the agent reads a reason rather than losing a call
    (FR-037).

    The port owns the waiting: by the time it answers, a held call has already
    been approved, rejected, expired or timed out. The gateway therefore sees
    only two outcomes and never has to know a call was held at all.
    """

    async def check_tool_call(
        self,
        *,
        run_context: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | None: ...


async def gated_upstream_call(
    params: dict[str, Any],
    gate: ToolCallGatePort | None,
    run_context: str | None,
    dispatch: UpstreamDispatch,
) -> Any:
    """Dispatch an upstream ``tools/call``, holding it first when a run owns it.

    The refusal is returned, never raised: a JSON-RPC error would reach the
    agent as "the gateway broke", and the one thing a held call must not look
    like is an upstream that is down (ADR *A Workflow Run's Writes Are Gated at
    the Gateway*, consequence four).
    """
    if gate is not None and run_context is not None:
        held = await gate.check_tool_call(
            run_context=run_context,
            tool_name=str(params.get("name") or ""),
            arguments=dict(params.get("arguments") or {}),
        )
        if held is not None:
            return held
    return await dispatch(handle_tools_call, params)


class LateBoundToolGate:
    """A gate that is not built yet when the session factory is.

    The gateway's session factory is built while the MCP kind is wired; the
    workflow gate cannot exist until after the chat platform is wired, several
    steps later. Rather than reorder the two — the MCP kind has to come first,
    because the gateway advertises the built-in tools the other kinds register
    — the factory is handed this, and the composition root binds the real gate
    into it once there is one.

    Unbound, it answers ``None`` to everything, which is the same answer as no
    gate at all: dispatch. So a session that opens during the window between
    the two wiring steps behaves exactly as an ungated one, rather than failing
    or blocking.
    """

    def __init__(self) -> None:
        self._inner: ToolCallGatePort | None = None

    def bind(self, gate: ToolCallGatePort) -> None:
        self._inner = gate

    async def check_tool_call(
        self,
        *,
        run_context: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any] | None:
        if self._inner is None:
            return None
        return await self._inner.check_tool_call(
            run_context=run_context, tool_name=tool_name, arguments=arguments
        )
