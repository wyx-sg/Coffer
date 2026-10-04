"""What the relay does to headers and bodies — which is almost nothing.

The contract (ADR api-key-providers-are-reached-through-a-separate-local-model-
proxy, "Relay"; Claude Code's gateway protocol page): ``anthropic-*`` headers
and body fields are an OPEN list, so nothing is allow-listed, reordered or
re-serialized. The request body goes upstream byte for byte; a copy is parsed
only for ``model`` and ``stream``. Headers are forwarded in order, duplicates
included, minus a short deny list:

- hop-by-hop headers (RFC 9110 §7.6.1) and any the ``Connection`` header names
  — they describe the client's connection to us, not ours to the upstream;
- ``host`` and ``content-length`` — the HTTP client writes its own;
- the client's credentials (``authorization``, ``x-api-key``, ``cookie``) and
  the proxy's control header — the proxy never forwards a client credential,
  it injects the member's own key;
- ``accept-encoding`` — replaced by ``identity``, so the usage reader sees plain
  SSE, and the proxy never has to compress toward the agent.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlsplit

from coffer.domain.model_proxy.state import CONTROL_TOKEN_HEADER, ProxyMember, UpstreamAuth
from coffer.domain.usage.records import Wire
from coffer.domain.usage.stream_usage import (
    AnthropicUsageReader,
    ResponsesUsageReader,
    UsageReader,
)
from coffer.infrastructure.net.loopback_authority import is_loopback_hostname

RawHeaders = list[tuple[bytes, bytes]]

HOP_BY_HOP: frozenset[bytes] = frozenset(
    {
        b"connection",
        b"keep-alive",
        b"proxy-authenticate",
        b"proxy-authorization",
        b"proxy-connection",
        b"te",
        b"trailer",
        b"transfer-encoding",
        b"upgrade",
    }
)

_REQUEST_DROP: frozenset[bytes] = HOP_BY_HOP | {
    b"host",
    b"content-length",
    b"authorization",
    b"x-api-key",
    b"cookie",
    b"accept-encoding",
    CONTROL_TOKEN_HEADER.encode(),
}

#: Attribution the agents send (Claude Code's gateway hint headers; Codex).
SESSION_HEADERS: tuple[bytes, ...] = (b"x-claude-code-session-id", b"session_id")
REQUEST_CLASS_HEADER = b"x-claude-code-request-class"


def _connection_named(headers: Iterable[tuple[bytes, bytes]]) -> set[bytes]:
    named: set[bytes] = set()
    for name, value in headers:
        if name.lower() == b"connection":
            named.update(p.strip().lower() for p in value.split(b",") if p.strip())
    return named


def header(headers: Iterable[tuple[bytes, bytes]], name: bytes) -> str | None:
    """The first value of ``name`` (lower-case), decoded as latin-1."""
    for key, value in headers:
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def upstream_request_headers(client: RawHeaders, member: ProxyMember) -> RawHeaders:
    """The client's headers minus the deny list, plus the member's key."""
    drop = _REQUEST_DROP | _connection_named(client)
    out: RawHeaders = [(k, v) for k, v in client if k.lower() not in drop]
    out.append((b"accept-encoding", b"identity"))
    key = member.key.encode("latin-1") if member.key else b""
    if key and member.auth is UpstreamAuth.ANTHROPIC:
        out.append((b"x-api-key", key))
        out.append((b"authorization", b"Bearer " + key))
    elif key and member.auth is UpstreamAuth.BEARER:
        out.append((b"authorization", b"Bearer " + key))
    return out


def client_response_headers(upstream: Iterable[tuple[bytes, bytes]]) -> RawHeaders:
    """Upstream response headers as relayed: everything but hop-by-hop and
    ``content-length`` (the body is re-framed chunk by chunk, so a relay that
    ends short is a framing error the agent notices, never a silent cut)."""
    items = list(upstream)
    drop = HOP_BY_HOP | {b"content-length"} | _connection_named(items)
    return [(k, v) for k, v in items if k.lower() not in drop]


def upstream_url(member: ProxyMember, endpoint: str, query: bytes) -> str:
    """``member.upstream_root`` + the path after the route prefix + the query."""
    url = member.upstream_root.rstrip("/") + endpoint
    if query:
        url += "?" + query.decode("latin-1")
    return url


def is_loopback_member(member: ProxyMember) -> bool:
    """A member reached without the user's ``HTTPS_PROXY``: a corporate proxy
    must never capture a leg that goes to this machine."""
    if member.local:
        return True
    host = urlsplit(member.upstream_root).hostname
    return bool(host) and is_loopback_hostname(host or "")


def request_meta(body: bytes) -> tuple[str | None, bool]:
    """``(model, stream)`` from a COPY of the request body; never raises."""
    try:
        payload: Any = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None, False
    if not isinstance(payload, dict):
        return None, False
    model = payload.get("model")
    return (model if isinstance(model, str) else None), payload.get("stream") is True


def new_reader(wire: Wire) -> UsageReader:
    return AnthropicUsageReader() if wire is Wire.ANTHROPIC else ResponsesUsageReader()


def error_body(wire: Wire | None, message: str, kind: str = "api_error") -> bytes:
    """An error in the wire's own shape, so the agent's error handling reads it."""
    if wire is Wire.ANTHROPIC:
        payload: dict[str, Any] = {"type": "error", "error": {"type": kind, "message": message}}
    else:
        payload = {"error": {"message": message, "type": kind}}
    return json.dumps(payload).encode()


__all__ = [
    "HOP_BY_HOP",
    "REQUEST_CLASS_HEADER",
    "SESSION_HEADERS",
    "RawHeaders",
    "client_response_headers",
    "error_body",
    "header",
    "is_loopback_member",
    "new_reader",
    "request_meta",
    "upstream_request_headers",
    "upstream_url",
]
