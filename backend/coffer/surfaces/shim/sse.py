"""The shim's server-initiated half: stream the daemon's SSE notifications to stdout.

Split out of :mod:`coffer.surfaces.shim.main` to keep that file small. The
bridge inherits :class:`SseDrain` and supplies the state and the two recovery
steps it leans on.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import httpx

_logger = logging.getLogger("coffer.shim")


class SseDrain:
    """Mixin: reconnecting ``GET /mcp`` stream forwarded line by line to stdout."""

    _stop: asyncio.Event
    _session_id: str | None
    _headers: dict[str, str]

    async def _recover(self, client: httpx.AsyncClient) -> bool:
        raise NotImplementedError

    async def _reinitialize(self, client: httpx.AsyncClient, stale: str) -> bool:
        raise NotImplementedError

    async def _drain_sse(self, client: httpx.AsyncClient) -> None:
        """After the first session id is known, stream notifications, reconnecting.

        A bounded reconnect loop around :meth:`_drain_sse_once`. The
        daemon may close the stream at any time (e.g. its idle-session reaper
        drops the session), and a single transient error must not silently stop
        server-initiated notifications (tools/list_changed, sampling, …) for the
        rest of a long-lived editor session. We reconnect with the same session
        id and an exponential backoff until ``_stop`` is set.
        """
        while not self._stop.is_set() and self._session_id is None:
            await asyncio.sleep(0.1)

        backoff = 0.5
        while not self._stop.is_set():
            healthy = await self._drain_sse_once(client)
            if self._stop.is_set():
                return
            # Reset backoff after a healthy stream; otherwise grow it.
            backoff = 0.5 if healthy else min(backoff * 2, 5.0)
            await asyncio.sleep(backoff)

    async def _drain_sse_once(self, client: httpx.AsyncClient) -> bool:
        """One SSE connection attempt. Open GET /mcp, forward each `data:` line
        to stdout until the stream ends or ``_stop`` is set.

        Returns True if a healthy (200) stream was served, False on a non-200
        status or a transport error (so the caller can back off before retry).
        """
        headers = {**self._headers, "Mcp-Session-Id": self._session_id or ""}
        try:
            async with client.stream("GET", "/mcp", headers=headers) as response:
                if response.status_code != 200:
                    _logger.warning(
                        "shim.sse_unexpected_status status=%s",
                        response.status_code,
                    )
                    if response.status_code == 404:
                        # The daemon dropped this session: handshake again, then
                        # the reconnect below carries the new id.
                        await self._reinitialize(client, headers["Mcp-Session-Id"])
                    if response.status_code == 401:
                        # The daemon restarted with a new token (see
                        # _handle_envelope). Without this the stream was
                        # retried every 5 s forever with the dead token.
                        await self._recover(client)
                    return False
                async for raw in response.aiter_lines():
                    if self._stop.is_set():
                        return True
                    if not raw or not raw.startswith("data:"):
                        continue
                    payload = raw[len("data:") :].strip()
                    if payload:
                        sys.stdout.write(payload + "\n")
                        sys.stdout.flush()
            return True
        except Exception as e:
            _logger.warning("shim.sse_disconnected", extra={"error": str(e)})
            return False
