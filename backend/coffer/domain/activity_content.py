"""What a tool call's recorded content may hold: redacted, then cut.

Spec mcp-gateway "Record invocations with redacted, bounded content". A call's
parts — its arguments, its result, an upstream's error text, a custom tool's
request and response — are captured here before anything is written, in the
spec's order:

1. every value Coffer injected into that upstream is replaced wherever it
   appears (the same :data:`MASK` and four-character floor as the stdio stderr
   mask and the one-off test, ``domain.mcp.probe``);
2. a credential header and the value of a secret-named field are replaced
   whole;
3. the part is serialised as JSON and cut at :data:`PART_LIMIT` bytes.

The plaintext-secret rules run afterwards, in the invocation writer: they are
infrastructure, and too slow for the call's own path.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

#: What a masked value reads as — the stdio stderr mask's and the one-off
#: test's marker (``domain.mcp.probe.REDACTED``), restated here because this
#: module is kind-agnostic and may not import the mcp kind.
MASK = "••••••"

#: A value shorter than this is not masked inside other text: replacing every
#: "1" or "on" protects nothing and makes the record unreadable.
_MIN_SECRET_LEN = 4

#: The most one part keeps, in UTF-8 bytes of its JSON.
PART_LIMIT = 16 * 1024

#: The parts a call can record, in the order a reader wants them.
PARTS = ("arguments", "result", "error", "request", "response")

#: Headers that carry a credential, compared lower-case.
_CREDENTIAL_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
    }
)
_HEADER_WORD = re.compile(r"token|secret|key|auth", re.IGNORECASE)

#: A field name that says its value is a secret: the whole name, or its last
#: ``_``/``-``/``.`` word (``api_token`` yes, ``max_tokens`` and
#: ``token_count`` no).
_SECRET_FIELD = re.compile(
    r"(?:^|[_\-.])(password|passwd|pwd|secret|token|api_?key|apikey|access_?key"
    r"|private_?key|client_?secret|credentials?|authorization|cookie)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CapturedPart:
    """One recorded part: its JSON (whole, or the first :data:`PART_LIMIT`
    bytes), whether it was cut, and its size before the cut."""

    text: str
    truncated: bool
    bytes: int

    def to_json(self) -> dict[str, Any]:
        return {"text": self.text, "truncated": self.truncated, "bytes": self.bytes}


def is_credential_header(name: str) -> bool:
    low = name.lower()
    return low in _CREDENTIAL_HEADERS or bool(_HEADER_WORD.search(low))


def is_secret_field(name: str) -> bool:
    return bool(_SECRET_FIELD.search(name))


def secret_values(values: Iterable[str]) -> tuple[str, ...]:
    """The values worth masking, longest first (a value containing another is
    replaced whole)."""
    unique = {v for v in values if v and len(v) >= _MIN_SECRET_LEN}
    return tuple(sorted(unique, key=len, reverse=True))


def _replace(text: str, values: tuple[str, ...]) -> str:
    for value in values:
        if value in text:
            text = text.replace(value, MASK)
    return text


def _redact(value: Any, values: tuple[str, ...], *, headers: bool = False) -> Any:
    if isinstance(value, str):
        return _replace(value, values)
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            whole = is_credential_header(key) if headers else is_secret_field(key)
            if whole and isinstance(v, str) and v:
                out[key] = MASK
            else:
                # A ``headers`` mapping anywhere below is read as headers.
                out[key] = _redact(v, values, headers=key.lower() == "headers")
        return out
    if isinstance(value, list | tuple):
        return [_redact(v, values, headers=headers) for v in value]
    return value


def cut(text: str, limit: int = PART_LIMIT) -> CapturedPart:
    """``text`` cut to ``limit`` UTF-8 bytes on a character boundary."""
    raw = text.encode()
    if len(raw) <= limit:
        return CapturedPart(text, False, len(raw))
    return CapturedPart(raw[:limit].decode(errors="ignore"), True, len(raw))


def capture(value: Any, secrets: Iterable[str] = ()) -> CapturedPart:
    """One part, redacted and cut. A value that is not JSON is recorded by its
    ``str``, masked the same way."""
    values = secret_values(secrets)
    redacted = _redact(value, values)
    try:
        text = json.dumps(redacted, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = _replace(str(value), values)
    return cut(text)


def capture_parts(parts: Mapping[str, Any], secrets: Iterable[str] = ()) -> dict[str, Any] | None:
    """Every part that is present, captured, keyed by part — or ``None`` when
    the call had nothing to record."""
    values = tuple(secrets)
    out = {
        name: capture(parts[name], values).to_json()
        for name in PARTS
        if name in parts and parts[name] is not None
    }
    return out or None


__all__ = [
    "MASK",
    "PARTS",
    "PART_LIMIT",
    "CapturedPart",
    "capture",
    "capture_parts",
    "cut",
    "is_credential_header",
    "is_secret_field",
]
