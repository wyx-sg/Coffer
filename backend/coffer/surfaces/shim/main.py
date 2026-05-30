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
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.infrastructure.daemon.spawn import daemon_spawn_command
from coffer.surfaces.cli._client import discover

_logger = logging.getLogger("coffer.shim")
_SHIM_LOG_DIR = Path.home() / ".coffer" / "logs"
_DAEMON_BOOT_TIMEOUT = 10  # seconds


def _setup_shim_log() -> None:
    """Send our diagnostic log to a file (NOT stdout — that's the MCP wire)."""
    try:
        _SHIM_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = _SHIM_LOG_DIR / f"shim-{os.getpid()}-{int(time.time())}.log"
        handler = logging.FileHandler(log_path)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        _logger.addHandler(handler)
        _logger.setLevel(logging.INFO)
    except OSError:
        # Failed to set up log file — continue without it
        pass


async def _wait_for_daemon(timeout: float) -> DaemonInfo | None:
    """Poll ~/.coffer/daemon.json until it appears + the daemon answers /status."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = discover()
        if info is not None:
            try:
                async with httpx.AsyncClient(
                    base_url=f"http://127.0.0.1:{info.port}/api/v1", timeout=2.0
                ) as c:
                    r = await c.get("/daemon/status")
                    if r.status_code == 200:
                        return info
            except Exception:
                pass
        await asyncio.sleep(0.2)
    return None


def _spawn_daemon() -> None:
    """Best-effort detached spawn of the coffer-daemon binary.

    Uses ``daemon_spawn_command()`` (ADR-006) so the correct binary is chosen
    whether the shim is running from source (dev/pip) or as a frozen
    PyInstaller bundle co-located with ``coffer-daemon``.
    """
    cmd = daemon_spawn_command()
    try:
        kwargs: dict[str, object] = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
            )
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(cmd, **kwargs)  # type: ignore[call-overload]
    except OSError as e:
        _logger.exception("shim.spawn_daemon_failed")
        sys.stderr.write(f"coffer-mcp-shim: failed to spawn daemon: {e}\n")


async def _ensure_daemon() -> DaemonInfo:
    """Return a DaemonInfo for a reachable daemon, spawning one if needed."""
    info = await _wait_for_daemon(timeout=1.0)
    if info is not None:
        return info
    _spawn_daemon()
    info = await _wait_for_daemon(timeout=_DAEMON_BOOT_TIMEOUT)
    if info is None:
        sys.stderr.write(
            f"coffer-mcp-shim: daemon did not come up within {_DAEMON_BOOT_TIMEOUT}s\n"
        )
        sys.exit(3)
    return info


class _Bridge:
    """One run of the bridge — stdin → POST, SSE → stdout."""

    def __init__(self, info: DaemonInfo) -> None:
        self._base = f"http://127.0.0.1:{info.port}"
        self._headers = {"X-Coffer-Token": info.token}
        self._session_id: str | None = None
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
        """Read JSON-RPC envelopes from stdin, POST to /mcp, write reply to stdout."""
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        _logger.info("shim.stdin_pump_started")

        while not self._stop.is_set():
            try:
                line = await reader.readline()
            except (ConnectionResetError, OSError):
                break
            if not line:
                # stdin EOF — request shutdown
                _logger.info("shim.stdin_eof")
                self._stop.set()
                return
            try:
                envelope = _json.loads(line.decode("utf-8").strip())
            except _json.JSONDecodeError as e:
                _logger.warning("shim.bad_json_from_stdin", extra={"error": str(e)})
                continue
            _logger.info(
                "shim.in method=%s id=%s",
                envelope.get("method"),
                envelope.get("id"),
            )

            headers = dict(self._headers)
            if self._session_id is not None:
                headers["Mcp-Session-Id"] = self._session_id

            try:
                response = await client.post("/mcp", json=envelope, headers=headers)
                _logger.info(
                    "shim.out status=%s len=%s",
                    response.status_code,
                    len(response.text or ""),
                )
            except Exception as e:
                _logger.exception("shim.post_failed")
                err = {
                    "jsonrpc": "2.0",
                    "id": envelope.get("id"),
                    "error": {"code": -32603, "message": f"shim: {e}"},
                }
                sys.stdout.write(_json.dumps(err) + "\n")
                sys.stdout.flush()
                continue

            if "Mcp-Session-Id" in response.headers:
                self._session_id = response.headers["Mcp-Session-Id"]

            # Stdout IS the MCP wire. If we ever write a non-JSON-RPC line
            # here the client crashes with JSONDecodeError on the very next
            # message. So: validate the gateway's response before forwarding.
            # On status / parse failure, synthesize a JSON-RPC error envelope
            # tied to the request id so the client sees a structured reply
            # rather than `Internal Server Error` plain text.
            self._forward_response(envelope, response)

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
