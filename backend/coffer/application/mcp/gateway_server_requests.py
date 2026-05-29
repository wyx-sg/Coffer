"""Server-initiated request bookkeeping for MCPGatewaySession (T-061/T-062).

Extracted from gateway.py to keep that module under 400 LOC.

When an upstream MCP server sends a sampling/createMessage or roots/list
request to coffer (acting as the MCP client), coffer must:
  1. Forward the request to the downstream client over the SSE channel.
  2. Wait for the downstream client to POST its response back.
  3. Return the response to the SDK so it can relay it to the upstream.

This module contains:
- _PendingRegistry  — manages the asyncio.Future dict and id counter
- build_sampling_callback  — factory for an SDK-compatible SamplingFnT
- build_list_roots_callback — factory for an SDK-compatible ListRootsFnT
- handle_response_from_downstream — shared matching logic
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import mcp.types as mcp_types
from mcp.shared.context import RequestContext

from coffer.domain.errors import UpstreamUnavailable

_logger = logging.getLogger(__name__)

# Type for the downstream SSE sink (same as NotificationSink in gateway.py)
DownstreamSink = Callable[[dict[str, Any]], Awaitable[None]]


class ServerRequestRegistry:
    """Tracks in-flight server-initiated requests and provides SDK callbacks.

    One instance per MCPGatewaySession.  The session passes its downstream_sink
    and client_capabilities references at callback-invocation time (via the
    factory closures below), so the registry itself stays pure-data.
    """

    def __init__(self) -> None:
        self._pending: dict[Any, asyncio.Future[Any]] = {}
        self._next_id: int = 0

    # ------------------------------------------------------------------
    # Core bookkeeping
    # ------------------------------------------------------------------

    async def send_request(
        self,
        method: str,
        params: dict[str, Any],
        downstream_sink: DownstreamSink | None,
        timeout: float = 30.0,
    ) -> Any:
        """Emit a JSON-RPC request to the downstream client and await the reply.

        Raises UpstreamUnavailable if no downstream is connected, or
        asyncio.TimeoutError if the reply doesn't arrive within `timeout` seconds.
        """
        if downstream_sink is None:
            raise UpstreamUnavailable(
                "no downstream client connected to forward server-initiated request"
            )
        self._next_id += 1
        req_id = self._next_id
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        # CODE-031: key the pending map by the STRING form of the id. JSON-RPC
        # allows an id to be a number or a string, and a compliant client may
        # echo our integer id back as a string ("1"). Normalising both the
        # store and the lookup to str makes the match type-agnostic so the
        # reply resolves the future instead of timing out after `timeout`s.
        self._pending[str(req_id)] = future
        try:
            await downstream_sink({"id": req_id, "method": method, "params": params})
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(str(req_id), None)

    def handle_response(self, envelope: dict[str, Any]) -> bool:
        """Try to match an incoming JSON-RPC response envelope to a pending request.

        Returns True if matched and consumed; False otherwise (caller should
        treat the envelope as a normal client request).
        """
        req_id = envelope.get("id")
        if req_id is None:
            return False
        # CODE-031: look up by the string form so an id echoed back as either a
        # number or a string matches the pending request stored under str(id).
        future = self._pending.get(str(req_id))
        if future is None or future.done():
            return False
        if "error" in envelope:
            err = envelope["error"]
            future.set_exception(
                RuntimeError(
                    err.get("message", "downstream error") if isinstance(err, dict) else str(err)
                )
            )
        else:
            future.set_result(envelope.get("result"))
        return True

    def cancel_all(self) -> None:
        """Cancel every in-flight future (called on session dispose)."""
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()


# ------------------------------------------------------------------
# SDK-compatible callback factories
# ------------------------------------------------------------------


def build_sampling_callback(
    registry: ServerRequestRegistry,
    get_sink: Callable[[], DownstreamSink | None],
    get_capabilities: Callable[[], dict[str, Any]],
    session_id: str,
) -> Any:  # returns SamplingFnT-compatible coroutine function
    """Build an async callable that the mcp SDK will invoke for sampling/createMessage."""

    async def _sampling_callback(
        context: RequestContext,  # type: ignore[type-arg]
        params: mcp_types.CreateMessageRequestParams,
    ) -> (
        mcp_types.CreateMessageResult | mcp_types.CreateMessageResultWithTools | mcp_types.ErrorData
    ):
        if "sampling" not in get_capabilities():
            _logger.debug(
                "mcp.gateway.sampling.capability_missing",
                extra={"session": session_id},
            )
            return mcp_types.ErrorData(
                code=mcp_types.METHOD_NOT_FOUND,
                message="downstream client does not support sampling",
            )
        raw_params: dict[str, Any] = (
            params.model_dump(exclude_none=True, mode="json")
            if hasattr(params, "model_dump")
            else (params if isinstance(params, dict) else {})
        )
        _logger.debug("mcp.gateway.sampling.forward", extra={"session": session_id})
        try:
            result = await registry.send_request("sampling/createMessage", raw_params, get_sink())
        except UpstreamUnavailable as e:
            return mcp_types.ErrorData(code=mcp_types.METHOD_NOT_FOUND, message=str(e))
        except Exception as e:
            return mcp_types.ErrorData(code=-32603, message=f"sampling failed: {e}")
        if isinstance(result, dict):
            try:
                return mcp_types.CreateMessageResult.model_validate(result)
            except Exception:
                pass
        return mcp_types.ErrorData(code=-32603, message="invalid sampling response from downstream")

    return _sampling_callback


def build_list_roots_callback(
    registry: ServerRequestRegistry,
    get_sink: Callable[[], DownstreamSink | None],
    session_id: str,
) -> Any:  # returns ListRootsFnT-compatible coroutine function
    """Build an async callable that the mcp SDK will invoke for roots/list."""

    async def _list_roots_callback(
        context: RequestContext,  # type: ignore[type-arg]
    ) -> mcp_types.ListRootsResult | mcp_types.ErrorData:
        _logger.debug("mcp.gateway.roots.forward", extra={"session": session_id})
        try:
            result = await registry.send_request("roots/list", {}, get_sink())
        except UpstreamUnavailable as e:
            return mcp_types.ErrorData(code=mcp_types.METHOD_NOT_FOUND, message=str(e))
        except Exception as e:
            return mcp_types.ErrorData(code=-32603, message=f"roots/list failed: {e}")
        if isinstance(result, dict):
            try:
                return mcp_types.ListRootsResult.model_validate(result)
            except Exception:
                pass
        return mcp_types.ListRootsResult(roots=[])

    return _list_roots_callback
