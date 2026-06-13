"""JSON-RPC 2.0 over stdio client for ``codex app-server`` (spec 008, T1).

``codex app-server`` speaks **newline-delimited JSON** (NDJSON) over stdin/stdout
— one JSON object per line, ``\\n``-terminated, in both directions (empirically
verified against codex-cli 0.125.0; see ``codex-approval-relay.plan.md`` §A). This
is *not* the LSP ``Content-Length`` framing.

The client drives that wire behind an injected reader/writer seam so turns are
unit-testable with no subprocess (mirrors ``cli_agent.Spawner`` /
``claude_sdk_agent.SdkSessionFactory``). The subprocess that supplies a real
reader/writer lives in ``codex_app_server.py``.

Three inbound frame kinds share one read loop and are demuxed by shape:

* ``{"id", "result"}`` / ``{"id", "error"}`` — a **response** to a client request;
  correlated to the pending future by ``id``.
* ``{"id", "method", "params"}`` — a **server→client request** (e.g. an approval);
  routed to the handler registered via :meth:`on_request`, whose return value is
  written back as ``{"id", "result"}``.
* ``{"method", "params"}`` (no ``id``) — a **notification**; pushed to the async
  iterator returned by :meth:`notifications`.

Malformed lines (non-JSON, blank, or unkeyed) are ignored so a stray line never
kills the loop. Only stdlib ``asyncio`` + ``json`` are used (Contract 9 — no new
dependency).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

_logger = logging.getLogger(__name__)

#: A server→client request handler: ``(params) -> result``.
RequestHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class _Reader(Protocol):
    async def readline(self) -> bytes: ...


class _Writer(Protocol):
    def write(self, data: bytes) -> None: ...

    async def drain(self) -> None: ...


class CodexRpcClient:
    """A bidirectional JSON-RPC peer over an injected NDJSON reader/writer.

    Call :meth:`start` once to spin up the inbound read loop, then use
    :meth:`request`, :meth:`on_request`, and :meth:`notifications`. Outbound
    frames are serialized with ``json.dumps(obj) + "\\n"`` (one object per line).
    """

    def __init__(self, reader: _Reader, writer: _Writer) -> None:
        self._reader = reader
        self._writer = writer
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._handlers: dict[str, RequestHandler] = {}
        self._notifications: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self._read_task: asyncio.Task[None] | None = None
        self._handler_tasks: set[asyncio.Task[None]] = set()
        self._write_lock = asyncio.Lock()
        self._eof = asyncio.Event()

    # -- lifecycle ---------------------------------------------------------

    @property
    def eof(self) -> asyncio.Event:
        """Event that is set when the inbound read loop has fully terminated.

        Set on all termination paths: normal EOF, exception, and :meth:`close`.
        Waiters can use ``await rpc.eof.wait()`` to detect peer stream end without
        reaching into private attributes.
        """
        return self._eof

    def start(self) -> None:
        """Spin up the inbound read loop (idempotent)."""
        if self._read_task is None:
            self._read_task = asyncio.create_task(self._read_loop())

    async def close(self) -> None:
        """Stop the read loop and fail any still-pending request futures."""
        if self._read_task is not None:
            self._read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._read_task
            self._read_task = None
        for task in list(self._handler_tasks):
            task.cancel()
        self._handler_tasks.clear()
        self._fail_pending(RuntimeError("codex rpc client closed"))
        # Guarantee _eof is set even if start() was never called so that any
        # waiter on eof.wait() does not hang after close().
        self._eof.set()

    # -- outbound ----------------------------------------------------------

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a client→server request and await its correlated result.

        Raises ``RuntimeError`` if the server replies with a JSON-RPC ``error``
        or the client is closed before the response arrives.
        """
        self._next_id += 1
        req_id = self._next_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[req_id] = future
        await self._write({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        return await future

    def on_request(self, method: str, handler: RequestHandler) -> None:
        """Register an async handler for an inbound server→client request method."""
        self._handlers[method] = handler

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send a client→server notification (no id, no response expected)."""
        frame: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            frame["params"] = params
        await self._write(frame)

    def notifications(self) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Async-iterate over inbound ``(method, params)`` notifications."""
        return self._notification_stream()

    async def _notification_stream(self) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        while True:
            yield await self._notifications.get()

    # -- internals ---------------------------------------------------------

    async def _write(self, obj: dict[str, Any]) -> None:
        data = (json.dumps(obj) + "\n").encode("utf-8")
        async with self._write_lock:
            self._writer.write(data)
            await self._writer.drain()

    async def _read_loop(self) -> None:
        try:
            while True:
                raw = await self._reader.readline()
                if not raw:  # EOF
                    break
                self._dispatch(raw)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.warning("codex_jsonrpc.read_loop_failed", exc_info=True)
        finally:
            self._fail_pending(RuntimeError("codex rpc stream ended"))
            self._eof.set()

    def _dispatch(self, raw: bytes) -> None:
        try:
            frame = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return  # malformed line — ignore
        if not isinstance(frame, dict):
            return
        has_id = "id" in frame
        has_method = "method" in frame
        if has_id and not has_method:
            self._handle_response(frame)
        elif has_id and has_method:
            self._handle_server_request(frame)
        elif has_method:
            self._handle_notification(frame)
        # else: unkeyed object — ignore

    def _handle_response(self, frame: dict[str, Any]) -> None:
        req_id = frame.get("id")
        if not isinstance(req_id, int):
            return
        future = self._pending.pop(req_id, None)
        if future is None or future.done():
            return
        if "error" in frame:
            err = frame["error"]
            message = err.get("message") if isinstance(err, dict) else str(err)
            future.set_exception(RuntimeError(f"codex rpc error: {message}"))
        else:
            result = frame.get("result")
            future.set_result(result if isinstance(result, dict) else {})

    def _handle_server_request(self, frame: dict[str, Any]) -> None:
        method = frame["method"]
        req_id = frame["id"]
        params = frame.get("params") or {}
        handler = self._handlers.get(method)
        if handler is None:
            _logger.info("codex_jsonrpc.unhandled_server_request", extra={"method": method})
            return
        task = asyncio.create_task(self._run_handler(handler, req_id, params))
        self._handler_tasks.add(task)
        task.add_done_callback(self._handler_tasks.discard)

    async def _run_handler(
        self, handler: RequestHandler, req_id: Any, params: dict[str, Any]
    ) -> None:
        try:
            result = await handler(params)
        except Exception:
            _logger.warning("codex_jsonrpc.request_handler_failed", exc_info=True)
            result = {}
        await self._write({"jsonrpc": "2.0", "id": req_id, "result": result})

    def _handle_notification(self, frame: dict[str, Any]) -> None:
        method = frame["method"]
        params = frame.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        self._notifications.put_nowait((method, params))

    def _fail_pending(self, exc: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(exc)
        self._pending.clear()


__all__ = ["CodexRpcClient", "RequestHandler"]
