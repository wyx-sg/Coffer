"""One request's attempts against the members of its route.

Same wire in, same wire out, bytes unchanged (ADR api-key-providers-are-
reached-through-a-separate-local-model-proxy, "Relay" and "Failover"). The
shape of one request:

1. Plan the candidates (:meth:`MemberBook.candidates`) — each tried once.
2. Per attempt, send the body byte for byte with the member's key injected
   (:mod:`.wire`). A connect/TLS/DNS error, or a first-byte (read) timeout,
   rests the member and moves on.
3. A non-2xx status is judged: 429, 5xx/529 and 401/403 move on while there is
   another candidate — the error body is kept, so if every later candidate
   fails to answer at all the agent still gets a real upstream response,
   verbatim; anything else (400, 404, 413, …) is the request's own problem and
   is relayed at once.
4. A streamed 2xx is HELD until its first content event (bounded by
   :attr:`RelayConfig.commit_max_bytes` / ``commit_max_seconds``). An
   ``event: error`` / ``response.failed`` that arrives first can still move to
   the next member invisibly. That is the commit point: after the first
   content byte reaches the agent the proxy never switches — a mid-stream
   error or truncation is passed through, marks the member, and the agent's
   own retry lands elsewhere.
5. Every attempt of a metered route writes one :class:`UsageRecord`, from a
   copy of the bytes fed to a usage reader. A reader that raises is dropped
   for the rest of that attempt; the relay never notices.

Nothing here logs a body, a prompt, a completion or a credential.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from starlette.types import Receive, Send

from coffer.domain.model_proxy.state import ProxyMember
from coffer.domain.usage.records import Outcome
from coffer.infrastructure.model_proxy import wire as w
from coffer.infrastructure.model_proxy.attempt import (
    Attempt,
    Held,
    RelayConfig,
    RelayRequest,
    ok_status,
    usage_record,
)
from coffer.infrastructure.model_proxy.downstream import (
    END,
    GONE,
    TIMEOUT,
    Broken,
    Downstream,
    cancel_quietly,
    next_item,
)
from coffer.infrastructure.model_proxy.members import MemberBook, parse_retry_after
from coffer.infrastructure.model_proxy.spool import UsageSpool

_logger = logging.getLogger(__name__)

_JSON = [(b"content-type", b"application/json")]


class Relay:
    """Relays requests for one proxy process; owns the upstream HTTP clients."""

    def __init__(
        self,
        book: MemberBook,
        spool: UsageSpool | None,
        config: RelayConfig | None = None,
    ) -> None:
        self.book = book
        self.spool = spool
        self.config = config or RelayConfig()
        c = self.config
        timeout = httpx.Timeout(None, connect=c.connect_timeout, read=c.read_timeout)
        # Remote members honour the user's HTTPS_PROXY / NO_PROXY (trust_env);
        # a loopback member is never sent through a proxy.
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
        if req.primary_only:
            candidates = req.route.members[:1]
        else:
            candidates = self.book.candidates(req.route, model, session_id)
        held: Held | None = None
        for index, member in enumerate(candidates):
            if down.gone.is_set():
                return
            attempt = Attempt(
                req=req,
                member=member,
                model=model,
                stream=stream,
                session_id=session_id,
                more=index < len(candidates) - 1,
                reader=w.new_reader(req.wire),
            )
            done, kept = await self._attempt(attempt, down)
            if done:
                return
            held = kept or held
        if down.gone.is_set():
            return
        if held is not None:
            await down.respond(held.status, held.headers, held.body)
            return
        message = "Coffer's model proxy could not reach any upstream for this connection."
        await down.respond(502, _JSON, w.error_body(req.wire, message))

    # --- one attempt -----------------------------------------------------------

    async def _attempt(self, a: Attempt, down: Downstream) -> tuple[bool, Held | None]:
        """``(done, held)`` — done when the agent has its answer (or left)."""
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
                return True, None
            response = sending.result()
        except Exception as exc:
            self.book.rest(member)
            a.outcome, a.failed_over = Outcome.CONNECT_ERROR, a.more
            self._log_failure(a, type(exc).__name__)
            self._finish(a)
            return False, None
        a.status = response.status_code
        a.request_id = response.headers.get("request-id") or response.headers.get("x-request-id")
        queue: asyncio.Queue[Any] = asyncio.Queue()
        down.queue = queue
        pump = asyncio.create_task(_pump(response, queue), name="model-proxy-pump")
        try:
            return await self._answer(a, down, response, queue)
        finally:
            down.queue = None
            await cancel_quietly(pump)
            await response.aclose()

    async def _answer(
        self, a: Attempt, down: Downstream, response: httpx.Response, queue: asyncio.Queue[Any]
    ) -> tuple[bool, Held | None]:
        status = response.status_code
        headers = w.client_response_headers(response.headers.raw)
        if not ok_status(status):
            a.outcome = Outcome.UPSTREAM_ERROR
            if self._judge_status(a.member, status, response) and a.more:
                body = await self._drain(queue, self.config.error_body_cap)
                a.failed_over = True
                self._log_failure(a, f"status {status}")
                self._finish(a)
                return False, Held(status, headers, body)
            await self._relay(a, down, status, headers, queue, [], sse=False)
            return True, None
        sse = response.headers.get("content-type", "").startswith("text/event-stream")
        if not sse or a.reader is None:
            await self._relay(a, down, status, headers, queue, [], sse=sse)
            return True, None
        held: list[bytes] = []
        size, deadline, tail = 0, time.monotonic() + self.config.commit_max_seconds, None
        while True:
            item = await next_item(queue, deadline - time.monotonic())
            if item is GONE:
                a.outcome = Outcome.CLIENT_CANCEL
                self._finish(a)
                return True, None
            if item is TIMEOUT:
                break
            if item is END or isinstance(item, Broken):
                tail = item
                break
            held.append(item)
            size += len(item)
            a.feed(item)
            reader = a.reader
            if reader is None or reader.first_content_seen:
                break
            if reader.saw_error_event:
                if not a.more:
                    break
                self.book.rest(a.member)
                a.outcome, a.failed_over = Outcome.ERROR_EVENT, True
                self._log_failure(a, "error event before content")
                self._finish(a)
                return False, Held(status, headers, b"".join(held))
            if size >= self.config.commit_max_bytes:
                break
        if isinstance(tail, Broken) and a.more:
            self.book.rest(a.member)
            a.outcome, a.failed_over = Outcome.TRUNCATED, True
            self._log_failure(a, "stream broke before content")
            self._finish(a)
            return False, None
        await self._relay(a, down, status, headers, queue, held, sse=True, tail=tail)
        return True, None

    def _judge_status(self, member: ProxyMember, status: int, response: httpx.Response) -> bool:
        """Mark the member for this status; True when the request may move on."""
        if status == 429:
            self.book.rate_limited(member, parse_retry_after(response.headers.get("retry-after")))
            return True
        if status in (401, 403):
            self.book.auth_failed(member)
            return True
        if status >= 500:
            self.book.rest(member)
            return True
        return False

    async def _drain(self, queue: asyncio.Queue[Any], cap: int) -> bytes:
        body = bytearray()
        while len(body) < cap:
            item = await next_item(queue, None)
            if item is END or item is GONE or isinstance(item, Broken):
                break
            body.extend(item)
        return bytes(body[:cap])

    # --- after the commit point --------------------------------------------------

    async def _relay(
        self,
        a: Attempt,
        down: Downstream,
        status: int,
        headers: w.RawHeaders,
        queue: asyncio.Queue[Any],
        prefix: list[bytes],
        *,
        sse: bool,
        tail: Any = None,
    ) -> None:
        """Send everything from here on, as it arrives, then settle the outcome."""
        copy: bytearray | None = None if sse or not ok_status(status) else bytearray()
        if not await down.start(status, headers):
            tail = GONE
        for chunk in prefix if tail is not GONE else []:
            if a.reader is None or a.reader.first_content_seen:
                a.mark_ttft()
            if not await down.body(chunk):
                tail = GONE
                break
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
            self.book.rest(a.member)
            self._log_failure(a, f"stream broke: {type(tail.error).__name__}")
        elif not ok_status(status):
            a.outcome = Outcome.UPSTREAM_ERROR
        else:
            self._settleok_status(a, sse, copy)
        self._finish(a)

    def _settleok_status(self, a: Attempt, sse: bool, copy: bytearray | None) -> None:
        reader = a.reader
        if reader is not None and copy is not None:
            try:
                reader.read_json(bytes(copy))
            except Exception:
                a.reader = reader = None
        if reader is not None and reader.saw_error_event:
            a.outcome = Outcome.ERROR_EVENT
            self.book.rest(a.member)
            self._log_failure(a, "error event after content")
        elif reader is not None and sse and not reader.saw_terminal:
            a.outcome = Outcome.TRUNCATED
            self.book.rest(a.member)
            self._log_failure(a, "stream ended before its terminal event")
        else:
            a.outcome = Outcome.COMPLETED
            self.book.served(a.member, a.req.agent.agent_uid, a.session_id)

    # --- accounting ----------------------------------------------------------------

    def _log_failure(self, a: Attempt, reason: str) -> None:
        _logger.warning(
            "model_proxy.member_failed agent=%s connection=%s endpoint=%s model=%s "
            "status=%s reason=%s failed_over=%s",
            a.req.agent.agent_uid,
            a.member.connection_uid,
            a.req.endpoint,
            a.model,
            a.status,
            reason,
            a.failed_over,
        )

    def _finish(self, a: Attempt) -> None:
        """Write this attempt's usage record, if the route is metered."""
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
