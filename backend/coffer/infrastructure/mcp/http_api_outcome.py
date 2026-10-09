"""What one custom-tool request returned, and how it is shown.

Spec mcp-gateway "Make a custom tool's request in the gateway", "Judge a custom
tool's answer by its group's response rules" and "Report what a custom tool's
test reached". :class:`HttpCallOutcome` is shared by the gateway's tool call
(``http_api_client``) and the page's test (``http_api_runner``), so both judge
and explain an answer the same way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from http import HTTPStatus

import httpx

from coffer.domain.mcp.http_api import HttpApiTool, HttpApiTransport
from coffer.domain.mcp.http_api_response import (
    SENSITIVE_HEADERS,
    ResponseRule,
    RuleFailure,
    rule_headers,
)

#: The most of a response body a tool returns (spec: "read at most 1 MiB").
MAX_RESPONSE_BYTES = 1024 * 1024
MASK = "***"
#: The response headers a test reports (spec mcp-gateway "Report what a custom
#: tool's test reached"): ids that name the request on the API's side, and who
#: answered when. Every other header — cookies, auth challenges, anything
#: unknown — is left out.
DIAGNOSTIC_HEADERS = frozenset(
    {
        "date",
        "server",
        "via",
        "retry-after",
        "x-request-id",
        "request-id",
        "x-correlation-id",
        "x-trace-id",
        "traceparent",
        "x-b3-traceid",
        "x-amzn-requestid",
        "x-amzn-trace-id",
        "x-amz-request-id",
        "x-amz-cf-id",
        "cf-ray",
    }
)
#: The longest diagnostic header value kept.
DIAGNOSTIC_VALUE_MAX = 256


@dataclass(frozen=True)
class ResponseCheck:
    """How one tool's answers are judged and which headers its result names."""

    rules: list[ResponseRule] = field(default_factory=list)
    #: The headers the group asked to see and the ones its rules read: reported
    #: by a test and named in every tool result.
    headers: frozenset[str] = frozenset()


def response_check(transport: HttpApiTransport, tool: HttpApiTool) -> ResponseCheck:
    rules = transport.rules_for(tool)
    named = set(transport.response.diagnostic_headers) | rule_headers(rules)
    return ResponseCheck(rules=list(rules), headers=frozenset(named - SENSITIVE_HEADERS))


class HttpCallOutcome:
    """What one request returned, before it is shaped into a tool result."""

    __slots__ = (
        "all_headers",
        "body",
        "body_bytes",
        "content_type",
        "duration_ms",
        "headers",
        "location",
        "named",
        "rule_failure",
        "status",
        "truncated",
        "url",
    )

    def __init__(
        self,
        *,
        url: str,
        status: int,
        body: str,
        truncated: bool,
        duration_ms: int,
        content_type: str | None,
        location: str | None,
        headers: dict[str, str] | None = None,
        body_bytes: int = 0,
        rule_failure: RuleFailure | None = None,
        named: frozenset[str] = frozenset(),
        all_headers: dict[str, str] | None = None,
    ) -> None:
        self.url = url
        #: Every response header, masked: what the call's record keeps.
        self.all_headers = all_headers or {}
        #: The reported response headers (:func:`diagnostic_headers`).
        self.headers = headers or {}
        #: The bytes of body read (at most :data:`MAX_RESPONSE_BYTES`).
        self.body_bytes = body_bytes
        #: The first response rule the answer broke; ``None`` when all held.
        self.rule_failure = rule_failure
        #: The headers the group asked to see (:attr:`ResponseCheck.headers`).
        self.named = named
        self.status = status
        self.body = body
        self.truncated = truncated
        self.duration_ms = duration_ms
        self.content_type = content_type
        self.location = location

    @property
    def is_error(self) -> bool:
        return self.status >= 400 or self.rule_failure is not None

    def status_line(self) -> str:
        try:
            reason = HTTPStatus(self.status).phrase
        except ValueError:
            reason = ""
        return f"HTTP {self.status} {reason}".rstrip()

    def as_text(self) -> str:
        """The tool result: the status line, the headers worth seeing — the
        ones the group named, every diagnostic one when the call failed — the
        failed rule, then the body (or a note that there was none)."""
        parts = [self.status_line()]
        if self.location is not None:
            parts.append(f"Location: {self.location} (not followed)")
        shown = (
            self.headers
            if self.is_error
            else {k: v for k, v in self.headers.items() if k in self.named}
        )
        parts.extend(f"{k}: {v}" for k, v in sorted(shown.items()))
        if self.rule_failure is not None:
            parts.append(f"Response rule failed: {self.rule_failure.describe()}")
        text = "\n".join(parts)
        if self.body:
            text += "\n\n" + self.body
        elif self.status:
            text += "\n\n(empty body)"
        if self.truncated:
            text += f"\n\n[response cut at {MAX_RESPONSE_BYTES} bytes]"
        return text


def mask_secrets(text: str, secrets: list[str]) -> str:
    for value in secrets:
        if value:
            text = text.replace(value, MASK)
    return text


def diagnostic_headers(
    headers: httpx.Headers, secrets: list[str], named: frozenset[str] = frozenset()
) -> dict[str, str]:
    """The built-in diagnostic headers and the ``named`` ones, names
    lower-cased, each value masked and cut to :data:`DIAGNOSTIC_VALUE_MAX`
    characters. A credential or cookie header is never reported."""
    out: dict[str, str] = {}
    for name, value in headers.items():
        key = name.lower()
        if key in SENSITIVE_HEADERS:
            continue
        if key in DIAGNOSTIC_HEADERS or key in named:
            out[key] = mask_secrets(value, secrets)[:DIAGNOSTIC_VALUE_MAX]
    return out


__all__ = [
    "DIAGNOSTIC_HEADERS",
    "DIAGNOSTIC_VALUE_MAX",
    "MASK",
    "MAX_RESPONSE_BYTES",
    "HttpCallOutcome",
    "ResponseCheck",
    "diagnostic_headers",
    "mask_secrets",
    "response_check",
]
