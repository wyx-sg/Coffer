"""A custom tool's request and response, as its call's content records them.

Spec mcp-gateway "Record invocations with redacted, bounded content". Built
inside the connection, where the call's own secrets are known, and masked with
them before they leave it; the gateway then masks credential headers whole and
cuts each part (``domain.activity_content``).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from coffer.domain.mcp.http_api_render import RenderedRequest

if TYPE_CHECKING:
    from coffer.infrastructure.mcp.http_api_outcome import HttpCallOutcome


def _body(text: str | None) -> Any:
    """JSON laid out as data when it parses, the text as it is otherwise."""
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        return text


def _mask(text: str, secrets: list[str]) -> str:
    for value in secrets:
        if value:
            text = text.replace(value, "***")
    return text


def request_record(request: RenderedRequest, secrets: list[str]) -> dict[str, Any]:
    body = request.body.decode(errors="replace") if request.body else None
    return {
        "method": request.method,
        "url": _mask(request.url, secrets),
        "headers": {k: _mask(v, secrets) for k, v in request.headers.items()},
        "body": _body(_mask(body, secrets) if body else None),
    }


def response_record(outcome: HttpCallOutcome, cut_at: int) -> dict[str, Any]:
    """The outcome's status, every header and its body (already masked)."""
    record: dict[str, Any] = {
        "status": outcome.status,
        "headers": dict(outcome.all_headers),
        "body": _body(outcome.body),
    }
    if outcome.truncated:
        record["body_cut_at_bytes"] = cut_at
    return record


__all__ = ["request_record", "response_record"]
