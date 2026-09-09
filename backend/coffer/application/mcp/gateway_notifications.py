"""Upstream → downstream notification forwarding for a gateway session.

Extracted from ``gateway.py`` to keep that module under the project's 400-LOC
ceiling. Pure routing: invalidate the right discovery cache slice, rewrite
resource URIs into Coffer's namespace, and forward. The session owns the
subscription bookkeeping; this owns what one notification means.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from coffer.application.mcp.discovery import CapabilityDiscovery
from coffer.application.mcp.gateway_parsing import _extract_method, _extract_params
from coffer.domain.mcp.namespace import prefix_resource_uri

SendDownstream = Callable[[dict[str, Any]], Awaitable[None]]

_LIST_CHANGED_SLICE = {
    "notifications/tools/list_changed": "tool",
    "notifications/resources/list_changed": "resource",
    "notifications/prompts/list_changed": "prompt",
}


async def forward_upstream_notification(
    server_name: str,
    notification: Any,
    *,
    discovery: CapabilityDiscovery,
    send_downstream: SendDownstream,
) -> None:
    """Handle one incoming notification from ``server_name``.

    Invalidates the appropriate discovery cache slice and forwards downstream
    (with URI rewriting for ``resources/updated``). Everything else —
    ``notifications/message``, ``notifications/progress`` — is dropped.
    """
    # The notification object's shape varies by SDK version; we look at
    # `method` (the JSON-RPC method name) and `params` defensively.
    method = _extract_method(notification)
    if method is None:
        return

    cache_slice = _LIST_CHANGED_SLICE.get(method)
    if cache_slice is not None:
        discovery.invalidate(server_name, cache_slice)  # type: ignore[arg-type]
        await send_downstream({"method": method, "params": {}})
        return

    if method == "notifications/resources/updated":
        raw_params = _extract_params(notification) or {}
        original_uri = raw_params.get("uri")
        if original_uri:
            raw_params = {**raw_params, "uri": prefix_resource_uri(server_name, original_uri)}
        await send_downstream({"method": method, "params": raw_params})


__all__ = ["forward_upstream_notification"]
