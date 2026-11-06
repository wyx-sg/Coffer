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
#: The longest response header value kept.
HEADER_VALUE_MAX = 256
#: Response headers whose value is a credential or a cookie: reported by name
#: with ``***`` as the value. An auth challenge (``WWW-Authenticate``) is not a
#: credential and is shown, since it says why a key was refused.
MASKED_RESPONSE_HEADERS = SENSITIVE_HEADERS - {"www-authenticate", "proxy-authenticate"}


@dataclass(frozen=True)
class ResponseCheck:
    """How one tool's answers are judged and which headers its result names."""

    rules: list[ResponseRule] = field(default_factory=list)
    #: The headers its rules read: named in every tool result.
    headers: frozenset[str] = frozenset()


def response_check(transport: HttpApiTransport, tool: HttpApiTool) -> ResponseCheck:
    rules = transport.rules_for(tool)
    headers = frozenset(rule_headers(rules) - SENSITIVE_HEADERS)
    return ResponseCheck(rules=list(rules), headers=headers)


class HttpCallOutcome:
    """What one request returned, before it is shaped into a tool result."""

    __slots__ = (
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
    ) -> None:
        self.url = url
        #: Every response header, masked (:func:`response_headers`): what a
        #: test reports and the call's record keeps.
        self.headers = headers or {}
        #: The bytes of body read (at most :data:`MAX_RESPONSE_BYTES`).
        self.body_bytes = body_bytes
        #: The first response rule the answer broke; ``None`` when all held.
        self.rule_failure = rule_failure
        #: The headers the group's rules read (:attr:`ResponseCheck.headers`).
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
        ones the group's rules read, every one when the call failed — the
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


def response_headers(headers: httpx.Headers, secrets: list[str]) -> dict[str, str]:
    """Every response header, names lower-cased: a credential or cookie
    header (:data:`MASKED_RESPONSE_HEADERS`) as ``***``, any other value with
    the call's secrets masked and cut to :data:`HEADER_VALUE_MAX` characters."""
    out: dict[str, str] = {}
    for name, value in headers.items():
        key = name.lower()
        out[key] = (
            MASK
            if key in MASKED_RESPONSE_HEADERS
            else mask_secrets(value, secrets)[:HEADER_VALUE_MAX]
        )
    return out


__all__ = [
    "HEADER_VALUE_MAX",
    "MASK",
    "MASKED_RESPONSE_HEADERS",
    "MAX_RESPONSE_BYTES",
    "HttpCallOutcome",
    "ResponseCheck",
    "mask_secrets",
    "response_check",
    "response_headers",
]
