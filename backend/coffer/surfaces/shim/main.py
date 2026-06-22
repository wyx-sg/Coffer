"""coffer-mcp-shim — stdio ↔ HTTP/SSE bridge.

Spawned by an MCP client (Claude Desktop / Cursor / Claude Code) as their
stdio MCP server. We forward every line on stdin as a POST to the coffer
daemon's /mcp endpoint, and every SSE message from the daemon back as a
line on stdout. If the daemon isn't running, we attempt to start it
ourselves (detect-or-spawn).

Exit codes:
   0  graceful exit (stdin EOF or SIGTERM)
   1  uncaught fatal error
   3  daemon unreachable / failed to spawn
"""

from __future__ import annotations

import asyncio
import contextlib
import json as _json
import logging
import os
import signal
import sys
from typing import Any

import httpx

from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.shim.bootstrap import (
    _ensure_daemon,
    _inject_cwd,
    _setup_shim_log,
    _wait_for_daemon,
)

_logger = logging.getLogger("coffer.shim")
# How long to wait for a live daemon when re-resolving after a connect failure
# (a restart rewrites daemon.json a moment before its port starts serving).
_RECOVER_TIMEOUT = 5  # seconds

# asyncio.StreamReader defaults to a 64 KiB (2**16) line limit; readline()
# then raises ValueError on any longer line, killing the stdin pump and
# silently dropping the request. MCP tool calls routinely exceed that (e.g. a
# confluence_update_page with a large page body), so raise the ceiling well
# past any realistic single JSON-RPC envelope while still bounding memory
# against a stream that never sends a newline.
_STDIN_READ_LIMIT = 64 * 1024 * 1024  # 64 MiB


class _Bridge:
    """One run of the bridge — stdin → POST, SSE → stdout."""

    def __init__(self, info: DaemonInfo) -> None:
        self._base = f"http://127.0.0.1:{info.port}"
        self._headers = {"X-Coffer-Token": info.token}
        self._session_id: str | None = None
        # The initialize envelope is cached at handshake time so it can be
        # replayed verbatim against a fresh daemon after a restart (the new
        # daemon has no knowledge of the old MCP session).
        self._init_envelope: dict[str, Any] | None = None
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> int:
        async with httpx.AsyncClient(
            base_url=self._base, headers=self._headers, timeout=httpx.Timeout(None)
        ) as client:
            stdin_task = asyncio.create_task(self._pump_stdin(client))
            sse_task = asyncio.create_task(self._drain_sse(client))

            _done, pending = await asyncio.wait(
                [stdin_task, sse_task, asyncio.create_task(self._stop.wait())],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            for t in pending:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t
        return 0

    async def _pump_stdin(self, client: httpx.AsyncClient) -> None:
        """Read JSON-RPC envelopes from stdin, POST to /mcp, write reply to stdout.

        CODE-M3: MCP clients pipeline requests (concurrent tool calls, ping
        keepalives, cancellations). Each envelope is dispatched as its own task
        so a single slow ``tools/call`` cannot head-of-line-block the others —
        previously the pump awaited every POST inline, starving pings until a
        client could declare the shim dead. Stdout stays uncorrupted because
        every write (``_forward_response`` / ``_emit_error``) emits a complete
        line + flush with no ``await`` in between, so concurrent tasks never
        interleave a partial line.
        """
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader(limit=_STDIN_READ_LIMIT)
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        _logger.info("shim.stdin_pump_started")

        inflight: set[asyncio.Task[None]] = set()
        while not self._stop.is_set():
            try:
                line = await reader.readline()
            except (ConnectionResetError, OSError):
                break
            if not line:
                # stdin EOF — drain below, then request shutdown
                _logger.info("shim.stdin_eof")
                break
            try:
                envelope = _json.loads(line.decode("utf-8").strip())
            except _json.JSONDecodeError as e:
                _logger.warning("shim.bad_json_from_stdin", extra={"error": str(e)})
                continue
            # FR-004: report the agent's launch cwd at session handshake so the
            # daemon can resolve the per-project memory store. We tuck it into
            # the ``initialize`` params under ``_meta`` (an MCP-reserved extension
            # key) so it rides the handshake; the gateway threads it into tools.
            if envelope.get("method") == "initialize":
                _inject_cwd(envelope)
                # Cache it so a daemon restart can be recovered transparently by
                # replaying the handshake against the new daemon (see _recover).
                self._init_envelope = dict(envelope)
            _logger.info(
                "shim.in method=%s id=%s",
                envelope.get("method"),
                envelope.get("id"),
            )

            # Establish the session synchronously on the first request so every
            # pipelined follow-up carries the same Mcp-Session-Id (clients wait
            # for initialize, but be defensive). Then dispatch concurrently.
            if self._session_id is None:
                await self._handle_envelope(client, envelope)
            else:
                task = asyncio.create_task(self._handle_envelope(client, envelope))
                inflight.add(task)
                task.add_done_callback(inflight.discard)

        # Drain in-flight handlers BEFORE signalling stop (CODE-R1): run()'s
        # FIRST_COMPLETED wait cancels this task the moment _stop fires, so
        # setting it first would abort the drain mid-POST and drop replies.
        if inflight:
            await asyncio.gather(*inflight, return_exceptions=True)
        self._stop.set()

    def _request_headers(self) -> dict[str, str]:
        headers = dict(self._headers)
        if self._session_id is not None:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    async def _handle_envelope(self, client: httpx.AsyncClient, envelope: dict[str, Any]) -> None:
        """POST one envelope to /mcp and forward the validated reply to stdout.

        If the POST fails to connect, the daemon may have restarted on a new
        port (its discovery file is rewritten on every boot). We re-resolve
        ``daemon.json`` once via :meth:`_recover`; if the endpoint moved we
        rebind to the live daemon, replay the cached ``initialize`` handshake,
        and retry this call once before surfacing an error. Without this a
        long-lived shim stayed pinned to the dead port forever, returning
        ``All connection attempts failed`` for every request.
        """
        try:
            response = await client.post("/mcp", json=envelope, headers=self._request_headers())
            _logger.info(
                "shim.out status=%s len=%s",
                response.status_code,
                len(response.text or ""),
            )
        except Exception as e:
            _logger.warning("shim.post_failed", extra={"error": type(e).__name__})
            if not await self._recover(client):
                self._emit_error(envelope.get("id"), code=-32603, message=f"shim: {e}")
                return
            try:
                response = await client.post("/mcp", json=envelope, headers=self._request_headers())
                _logger.info(
                    "shim.out_after_recover status=%s len=%s",
                    response.status_code,
                    len(response.text or ""),
                )
            except Exception as e2:
                _logger.exception("shim.post_failed_after_recover")
                self._emit_error(envelope.get("id"), code=-32603, message=f"shim: {e2}")
                return

        if "Mcp-Session-Id" in response.headers:
            self._session_id = response.headers["Mcp-Session-Id"]

        # Stdout IS the MCP wire. If we ever write a non-JSON-RPC line here the
        # client crashes with JSONDecodeError on the very next message. So:
        # validate the gateway's response before forwarding. On status / parse
        # failure, synthesize a JSON-RPC error envelope tied to the request id
        # so the client sees a structured reply rather than plain text.
        self._forward_response(envelope, response)

    async def _recover(self, client: httpx.AsyncClient) -> bool:
        """Re-resolve ``daemon.json`` after a transport failure.

        Returns True only when a *live* daemon is found at an endpoint that
        differs from the one we are pinned to (a restart on a new port and/or a
        rotated token). In that case we rebind the shared client to it, drop the
        now-defunct session id, replay the cached ``initialize`` handshake to
        establish a fresh session, and let the caller retry.

        Returns False for a genuine transient blip against the *same* live
        endpoint (let normal retry/backoff handle it) and when no daemon is
        reachable at all (the caller surfaces an error; a fresh shim spawn is
        the recovery path for a fully-down daemon, not an in-place spin).
        """
        info = await _wait_for_daemon(timeout=_RECOVER_TIMEOUT)
        if info is None:
            return False
        new_base = f"http://127.0.0.1:{info.port}"
        if new_base == self._base and info.token == self._headers.get("X-Coffer-Token"):
            return False
        _logger.warning("shim.daemon_moved old=%s new_port=%s", self._base, info.port)
        self._base = new_base
        self._headers["X-Coffer-Token"] = info.token
        client.base_url = new_base
        client.headers["X-Coffer-Token"] = info.token
        # The new daemon never saw the old session; force a fresh handshake.
        self._session_id = None
        await self._replay_initialize(client)
        return True

    async def _replay_initialize(self, client: httpx.AsyncClient) -> None:
        """Re-run the cached ``initialize`` against the (rebound) daemon so a
        new MCP session is established before the caller retries. The reply is
        NOT forwarded to stdout — the MCP client already received its original
        initialize response and must not see a duplicate."""
        if self._init_envelope is None:
            return
        response = await client.post("/mcp", json=self._init_envelope, headers=dict(self._headers))
        if "Mcp-Session-Id" in response.headers:
            self._session_id = response.headers["Mcp-Session-Id"]

    def _forward_response(
        self,
        envelope: dict[str, Any],
        response: httpx.Response,
    ) -> None:
        req_id = envelope.get("id")
        raw_body = (response.text or "").strip()
        if response.status_code >= 400:
            _logger.warning(
                "shim.gateway_error_status",
                extra={"status": response.status_code, "body_head": raw_body[:200]},
            )
            body_excerpt = raw_body[:200] or "(empty body)"
            self._emit_error(
                req_id,
                code=-32603,
                message=f"coffer gateway HTTP {response.status_code}: {body_excerpt}",
            )
            return
        if not raw_body:
            # 2xx with empty body is allowed by /mcp for matched-response acks;
            # nothing to forward.
            return
        try:
            _json.loads(raw_body)
        except _json.JSONDecodeError as e:
            _logger.warning(
                "shim.non_json_2xx",
                extra={"error": str(e), "body_head": raw_body[:200]},
            )
            self._emit_error(
                req_id,
                code=-32603,
                message=f"coffer gateway returned non-JSON 2xx: {raw_body[:200]}",
            )
            return
        sys.stdout.write(raw_body + "\n")
        sys.stdout.flush()

    def _emit_error(self, req_id: Any, code: int, message: str) -> None:
        err = {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }
        sys.stdout.write(_json.dumps(err) + "\n")
        sys.stdout.flush()

    async def _drain_sse(self, client: httpx.AsyncClient) -> None:
        """After the first session id is known, stream notifications, reconnecting.

        CODE-046: a bounded reconnect loop around :meth:`_drain_sse_once`. The
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
                        "shim.sse_unexpected_status",
                        extra={"status": response.status_code},
                    )
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


async def _async_main() -> int:
    _setup_shim_log()
    _logger.info("shim.start pid=%s", os.getpid())
    info = await _ensure_daemon()
    _logger.info("shim.daemon port=%s", info.port)
    bridge = _Bridge(info)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, bridge.stop)

    return await bridge.run()


def run() -> None:
    """Entry point for `coffer-mcp-shim`."""
    try:
        code = asyncio.run(_async_main())
    except KeyboardInterrupt:
        code = 0
    except SystemExit as e:
        code = int(e.code) if e.code is not None else 0
    except Exception as e:
        sys.stderr.write(f"coffer-mcp-shim: fatal: {e}\n")
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    run()
