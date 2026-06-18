"""HTTP client for the official MCP Registry (ADR-029).

The registry is an open, unauthenticated, **preview** metadata API. We fetch the
``GET /v0.1/servers`` list endpoint (substring name search) and return raw entry
dicts for the domain mapper to normalize. Any network/HTTP/JSON failure becomes
``RegistryUnavailable`` so the surface degrades to a clear 502 (the paste-JSON
add path stays usable).
"""

from __future__ import annotations

from typing import Any

import httpx

from coffer.domain.mcp.registry import RegistryUnavailable

_REGISTRY_BASE_URL = "https://registry.modelcontextprotocol.io"
_SEARCH_PATH = "/v0.1/servers"
_TIMEOUT_SECONDS = 10.0


class HttpMCPRegistryClient:
    """Fetches server entries from the official MCP Registry over HTTPS."""

    def __init__(
        self,
        base_url: str = _REGISTRY_BASE_URL,
        timeout_seconds: float = _TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    async def fetch_servers(self, query: str, limit: int) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"search": query, "limit": limit, "version": "latest"}
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(self._timeout)) as client:
                resp = await client.get(f"{self._base_url}{_SEARCH_PATH}", params=params)
                resp.raise_for_status()
                body = resp.json()
        except (httpx.HTTPError, ValueError) as e:
            # type name only — upstream error text may echo request details.
            raise RegistryUnavailable(f"MCP registry request failed: {type(e).__name__}") from e
        servers = body.get("servers") if isinstance(body, dict) else None
        if not isinstance(servers, list):
            return []
        return [s for s in servers if isinstance(s, dict)]
