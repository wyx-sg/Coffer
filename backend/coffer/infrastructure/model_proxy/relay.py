"""One request's relay to its connection's upstream.

Same wire in, same wire out, bytes unchanged (ADR api-key-providers-are-
reached-through-a-separate-local-model-proxy, "Relay"). A request goes to
exactly one upstream: the connection the agent is on. The shape of one request:

1. Send the body byte for byte with the connection's key injected
   (:mod:`.wire`). If the upstream cannot be reached at all — a connect, TLS
   or DNS error, or a first-byte (read) timeout — the agent gets a 502.
2. Whatever the upstream answers, status included, is relayed as it arrives:
   an error status and its body reach the agent verbatim, and a mid-stream
   error or truncation is passed through. The agent's own retry is the only
   retry there is.
3. Every request of a metered route writes one :class:`UsageRecord`, from a
   copy of the bytes fed to a usage reader. A reader that raises is dropped
   for the rest of that request; the relay never notices.

Nothing here logs a body, a prompt, a completion or a secret.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from starlette.types import Receive, Send

from coffer.domain.usage.records import Outcome
from coffer.infrastructure.model_proxy import wire as w
from coffer.infrastructure.model_proxy.attempt import (
    Attempt,
    RelayConfig,
    RelayRequest,
    ok_status,
    usage_record,
)
from coffer.infrastructure.model_proxy.downstream import (
    END,
    GONE,
    Broken,
    Downstream,
    cancel_quietly,
    next_item,
)
from coffer.infrastructure.model_proxy.spool import UsageSpool

_logger = logging.getLogger(__name__)

_JSON = [(b"content-type", b"application/json")]


class Relay:
    """Relays requests for one proxy process; owns the upstream HTTP clients."""

    def __init__(
        self,
        spool: UsageSpool | None,
        config: RelayConfig | None = None,
    ) -> None:
        self.spool = spool
        self.config = config or RelayConfig()
        c = self.config
        timeout = httpx.Timeout(None, connect=c.connect_timeout, read=c.read_timeout)
        # A remote upstream honours the user's HTTPS_PROXY / NO_PROXY (trust_env);
        # a loopback upstream is never sent through a proxy.
        self._remote = httpx.AsyncClient(timeout=timeout, trust_env=True)
        self._local = httpx.AsyncClient(timeout=timeout, trust_env=False)

    async def aclose(self) -> None:
        await self._remote.aclose()
        await self._local.aclose()

    async def serve(self, req: RelayRequest, receive: Receive, send: Send) -> None:
        down = Downstream(receive, send)
        watcher = asyncio.create_task(down.watch(), name="model-proxy-disconnect")
        try:
            await self._serve(req, down)
        finally:
            await cancel_quietly(watcher)

    async def _serve(self, req: RelayRequest, down: Downstream) -> None:
        model, stream = w.request_meta(req.body)
        session_id = next((v for n in w.SESSION_HEADERS if (v := w.header(req.headers, n))), None)
        attempt = Attempt(
            req=req,
            member=req.route.member,
            model=model,
            stream=stream,
            session_id=session_id,
            reader=w.new_reader(req.wire),
        )
        if await self._attempt(attempt, down) or down.gone.is_set():
            return
        message = "Coffer's model proxy could not reach the upstream for this connection."
        await down.respond(502, _JSON, w.error_body(req.wire, message))

    # --- the attempt -----------------------------------------------------------

    async def _attempt(self, a: Attempt, down: Downstream) -> bool:
        """True when the agent has its answer (or left); False when the
        upstream could not be reached at all."""
        req, member = a.req, a.member
        http = self._local if w.is_loopback_member(member) else self._remote
        sending: asyncio.Future[httpx.Response] | None = None
        try:
            request = http.build_request(
                req.method,
                w.upstream_url(member, req.endpoint, req.query),
                headers=w.upstream_request_headers(req.headers, member),
                content=req.body if req.method != "GET" else None,
            )
            sending = asyncio.ensure_future(http.send(request, stream=True))
            gone = asyncio.ensure_future(down.gone.wait())
            await asyncio.wait({sending, gone}, return_when=asyncio.FIRST_COMPLETED)
            await cancel_quietly(gone)
            if not sending.done():
                await cancel_quietly(sending)
                a.outcome = Outcome.CLIENT_CANCEL
                self._finish(a)
                return True
            response = sending.result()
        except Exception as exc:
            a.outcome = Outcome.CONNECT_ERROR
            self._log_failure(a, type(exc).__name__)
            self._finish(a)
            return False
        a.status = response.status_code
        a.request_id = response.headers.get("request-id") or response.headers.get("x-request-id")
        queue: asyncio.Queue[Any] = asyncio.Queue()
        down.queue = queue
        pump = asyncio.create_task(_pump(response, queue), name="model-proxy-pump")
        try:
            status = response.status_code
            headers = w.client_response_headers(response.headers.raw)
            sse = response.headers.get("content-type", "").startswith("text/event-stream")
            await self._relay(a, down, status, headers, queue, sse=sse and ok_status(status))
            return True
        finally:
            down.queue = None
            await cancel_quietly(pump)
            await response.aclose()

    # --- the response ------------------------------------------------------------

    async def _relay(
        self,
        a: Attempt,
        down: Downstream,
        status: int,
        headers: w.RawHeaders,
        queue: asyncio.Queue[Any],
        *,
        sse: bool,
    ) -> None:
        """Send everything as it arrives, then settle the outcome."""
        copy: bytearray | None = None if sse or not ok_status(status) else bytearray()
        tail: Any = None
        if not await down.start(status, headers):
            tail = GONE
        while tail is None:
            item = await next_item(queue, None)
            if item is END or item is GONE or isinstance(item, Broken):
                tail = item
                break
            if sse:
                a.feed(item)
                if a.reader is None or a.reader.first_content_seen:
                    a.mark_ttft()
            else:
                a.mark_ttft()
                if copy is not None and len(copy) < self.config.reader_body_cap:
                    copy.extend(item)
            if not await down.body(item):
                tail = GONE
        if tail is not GONE:
            await down.body(b"", more=False)
        if tail is GONE:
            a.outcome = Outcome.CLIENT_CANCEL
        elif isinstance(tail, Broken):
            a.outcome = Outcome.TRUNCATED
            self._log_failure(a, f"stream broke: {type(tail.error).__name__}")
        elif not ok_status(status):
            a.outcome = Outcome.UPSTREAM_ERROR
        else:
            self._settle_ok(a, sse, copy)
        self._finish(a)

    def _settle_ok(self, a: Attempt, sse: bool, copy: bytearray | None) -> None:
        reader = a.reader
        if reader is not None and copy is not None:
            try:
                reader.read_json(bytes(copy))
            except Exception:
                a.reader = reader = None
        if reader is not None and reader.saw_error_event:
            a.outcome = Outcome.ERROR_EVENT
            self._log_failure(a, "error event")
        elif reader is not None and sse and not reader.saw_terminal:
            a.outcome = Outcome.TRUNCATED
            self._log_failure(a, "stream ended before its terminal event")
        else:
            a.outcome = Outcome.COMPLETED

    # --- accounting ----------------------------------------------------------------

    def _log_failure(self, a: Attempt, reason: str) -> None:
        _logger.warning(
            "model_proxy.upstream_failed agent=%s connection=%s endpoint=%s model=%s "
            "status=%s reason=%s",
            a.req.agent.agent_uid,
            a.member.connection_uid,
            a.req.endpoint,
            a.model,
            a.status,
            reason,
        )

    def _finish(self, a: Attempt) -> None:
        """Write this request's usage record, if the route is metered."""
        if not a.req.metered or self.spool is None:
            return
        try:
            self.spool.append(usage_record(a))
        except Exception:
            _logger.warning("model_proxy.usage_record_failed", exc_info=True)


async def _pump(response: httpx.Response, queue: asyncio.Queue[Any]) -> None:
    """Move upstream chunks into ``queue`` as received — raw, never decoded."""
    try:
        async for chunk in response.aiter_raw():
            if chunk:
                queue.put_nowait(chunk)
    except Exception as exc:
        queue.put_nowait(Broken(exc))
        return
    queue.put_nowait(END)


__all__ = ["Relay", "RelayConfig", "RelayRequest"]
