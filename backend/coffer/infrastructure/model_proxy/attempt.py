"""The pieces of one upstream attempt the relay tracks, and the usage record
it turns into.

Split from :mod:`.relay` so the relay reads as control flow: here is only the
data — the request as the app hands it over, the per-attempt accounting
(status, outcome, time to first content, the usage reader fed beside the
relay) and the one function that turns that accounting into the
:class:`~coffer.domain.usage.records.UsageRecord` the spool writes. The record
holds metadata and token counts only — never a body or a secret.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from coffer.domain.model_proxy.state import ProxyAgent, ProxyMember, ProxyRoute
from coffer.domain.usage.records import Outcome, UsageRecord, Wire
from coffer.domain.usage.stream_usage import UsageReader
from coffer.infrastructure.model_proxy import wire as w


@dataclass(frozen=True)
class RelayConfig:
    connect_timeout: float = 10.0
    #: Upstream read idleness — also the first-byte timeout. Both agents'
    #: own stream watchdogs are 300 s, so anything shorter would cut a slow
    #: but healthy answer.
    read_timeout: float = 300.0
    commit_max_bytes: int = 64 * 1024
    commit_max_seconds: float = 5.0
    #: How much of an error body is kept while failing over.
    error_body_cap: int = 1024 * 1024
    #: How much of a non-streamed body is copied for the usage reader.
    reader_body_cap: int = 32 * 1024 * 1024


@dataclass(frozen=True)
class RelayRequest:
    wire: Wire
    #: The path after the route prefix (``/v1/messages``).
    endpoint: str
    method: str
    query: bytes
    headers: w.RawHeaders
    body: bytes
    agent: ProxyAgent
    route: ProxyRoute
    metered: bool
    primary_only: bool = False


@dataclass
class Held:
    status: int
    headers: w.RawHeaders
    body: bytes


@dataclass
class Attempt:
    req: RelayRequest
    member: ProxyMember
    model: str | None
    stream: bool
    session_id: str | None
    more: bool
    reader: UsageReader | None
    attempt_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    t0: float = field(default_factory=time.monotonic)
    status: int | None = None
    request_id: str | None = None
    outcome: Outcome = Outcome.CONNECT_ERROR
    failed_over: bool = False
    ttft_ms: int | None = None

    def feed(self, chunk: bytes) -> None:
        if self.reader is None:
            return
        try:
            self.reader.feed(chunk)
        except Exception:
            self.reader = None  # metering gap, never a relay failure

    def mark_ttft(self) -> None:
        if self.ttft_ms is None:
            self.ttft_ms = int((time.monotonic() - self.t0) * 1000)


def ok_status(status: int | None) -> bool:
    return status is not None and 200 <= status < 300


def usage_record(a: Attempt) -> UsageRecord:
    usage = a.reader.usage() if a.reader is not None and ok_status(a.status) else None
    req = a.req
    return UsageRecord(
        dedupe_key=a.request_id or f"attempt:{a.attempt_id}",
        attempt_id=a.attempt_id,
        started_at=a.started_at,
        agent_uid=req.agent.agent_uid,
        agent_type=req.agent.agent_type,
        session_id=a.session_id,
        request_class=w.header(req.headers, w.REQUEST_CLASS_HEADER),
        connection_uid=a.member.connection_uid,
        member=a.member.connection_name,
        wire=req.wire,
        endpoint=req.endpoint,
        model=a.model,
        stream=a.stream,
        status=a.status,
        outcome=a.outcome,
        failed_over=a.failed_over,
        ttft_ms=a.ttft_ms,
        duration_ms=int((time.monotonic() - a.t0) * 1000),
        usage_known=usage is not None,
        input_tokens=usage.input_tokens if usage else None,
        cache_write_5m_tokens=usage.cache_write_5m_tokens if usage else None,
        cache_write_1h_tokens=usage.cache_write_1h_tokens if usage else None,
        cache_read_tokens=usage.cache_read_tokens if usage else None,
        output_tokens=usage.output_tokens if usage else None,
        reasoning_tokens=usage.reasoning_tokens if usage else None,
        web_search_requests=usage.web_search_requests if usage else None,
        speed=usage.speed if usage else None,
        inference_geo=usage.inference_geo if usage else None,
        upstream_request_id=a.request_id,
    )


__all__ = ["Attempt", "Held", "RelayConfig", "RelayRequest", "ok_status", "usage_record"]
