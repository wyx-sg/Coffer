"""How a custom tool's answer is judged and explained.

Spec mcp-gateway "Judge a custom tool's answer by its group's response rules"
and "Report what a custom tool's test reached". An HTTP status of 400 or more is
always a failure. Past that, an API may say "failed" in a header or a JSON field
of a 200 answer; a group (or one tool) declares where to look with
:class:`ResponseRule` rows — read one value from the status, a response header
or a JSON Pointer into the body, and name the values that mean success. Nothing
here knows any API: every header name, pointer and value comes from the rows.

A group may also name extra response headers to report (beside the built-in
request and trace ids). A header that carries credentials or cookies can never
be named, as a diagnostic header or by a rule.

Pure: Pydantic and the standard library only.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from coffer.domain.mcp.http_api_headers import HEADER_NAME_RE

#: Response headers that are never reported nor read by a rule: they carry
#: credentials, cookies or auth challenges.
SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "set-cookie2",
        "www-authenticate",
        "proxy-authenticate",
        "x-api-key",
        "api-key",
    }
)
#: The most rules, diagnostic headers and success values one place holds.
MAX_RULES = 10
MAX_DIAGNOSTIC_HEADERS = 20
MAX_OK_VALUES = 20
#: The longest success value, JSON Pointer, and reported value or message.
MAX_VALUE_LENGTH = 200
MAX_POINTER_LENGTH = 200
REPORTED_VALUE_MAX = 256

ValueSource = Literal["status", "header", "json"]
MessageSource = Literal["header", "json"]


def _header_name(value: str) -> str:
    name = value.strip().lower()
    if not HEADER_NAME_RE.match(name):
        raise ValueError(f"{value!r} is not a valid header name")
    if name in SENSITIVE_HEADERS:
        raise ValueError(f"{name!r} carries credentials or cookies and cannot be read")
    return name


def _pointer(value: str) -> str:
    if not value.startswith("/") or len(value) > MAX_POINTER_LENGTH:
        raise ValueError(
            f"{value!r} is not a JSON Pointer: start it with '/' (like /code or /error/code)"
        )
    return value


def _checked_name(source: str, name: str) -> str:
    if source == "status":
        if name:
            raise ValueError("a status rule takes no name")
        return ""
    if not name:
        raise ValueError(f"a {source} rule needs a name")
    return _header_name(name) if source == "header" else _pointer(name)


class ResponseField(BaseModel):
    """Where a rule's error message is read: a response header or a JSON Pointer."""

    source: MessageSource
    name: str

    @model_validator(mode="after")
    def _name(self) -> ResponseField:
        self.name = _checked_name(self.source, self.name)
        return self


class ResponseRule(BaseModel):
    """One value of the answer and the values that mean success.

    ``missing`` says what an answer without the value means (a header not sent,
    a pointer that names nothing, a body that is not JSON). ``message`` names
    where the API puts its own error text, reported beside a failure.
    """

    source: ValueSource
    #: The header name (case-insensitive) or the JSON Pointer; empty for status.
    name: str = ""
    ok_values: list[str] = Field(min_length=1, max_length=MAX_OK_VALUES)
    missing: Literal["ok", "error"] = "ok"
    message: ResponseField | None = None

    @field_validator("ok_values")
    @classmethod
    def _values(cls, v: list[str]) -> list[str]:
        if any(len(x) > MAX_VALUE_LENGTH for x in v):
            raise ValueError(f"a success value is at most {MAX_VALUE_LENGTH} characters")
        return v

    @model_validator(mode="after")
    def _shape(self) -> ResponseRule:
        self.name = _checked_name(self.source, self.name)
        if self.source == "status" and any(not _is_status(x) for x in self.ok_values):
            raise ValueError("a status rule's success values are HTTP statuses (100-599)")
        return self

    @property
    def label(self) -> str:
        return "status" if self.source == "status" else f"{self.source} {self.name}"


def _is_status(value: str) -> bool:
    return value.isdigit() and 100 <= int(value) <= 599


class HttpApiResponse(BaseModel):
    """A group's response settings: extra headers to report and its rules."""

    #: Response headers reported beside the built-in request and trace ids.
    diagnostic_headers: list[str] = Field(default_factory=list, max_length=MAX_DIAGNOSTIC_HEADERS)
    #: Every rule must hold for an answer to count as a success.
    rules: list[ResponseRule] = Field(default_factory=list, max_length=MAX_RULES)

    @field_validator("diagnostic_headers")
    @classmethod
    def _headers(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for name in v:
            checked = _header_name(name)
            if checked not in out:
                out.append(checked)
        return out


def rule_headers(rules: list[ResponseRule]) -> set[str]:
    """Every response header a rule reads, its value or its message."""
    names = {r.name for r in rules if r.source == "header"}
    names |= {r.message.name for r in rules if r.message and r.message.source == "header"}
    return names


@dataclass(frozen=True)
class RuleFailure:
    """The first rule an answer broke, for the result to explain."""

    rule: ResponseRule
    #: The value read, cut; ``None`` when the answer did not carry it.
    value: str | None
    #: The API's own error text, cut; ``None`` when there is none.
    message: str | None

    def describe(self) -> str:
        expected = ", ".join(json.dumps(v) for v in self.rule.ok_values)
        if self.value is None:
            text = f"{self.rule.label} is missing (success: {expected})"
        else:
            text = f"{self.rule.label} = {json.dumps(self.value)} (success: {expected})"
        if self.message:
            text += f": {self.message}"
        return text


_MISSING = object()


def _resolve_pointer(doc: Any, pointer: str) -> Any:
    """RFC 6901: ``/a/0/b``; ``_MISSING`` when it names nothing."""
    node = doc
    for raw in pointer.split("/")[1:]:
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            if part not in node:
                return _MISSING
            node = node[part]
        elif isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                return _MISSING
            node = node[int(part)]
        else:
            return _MISSING
    return node


def _as_text(value: Any) -> str:
    """A JSON value as the text success values are compared with: a string
    as it is, ``0`` / ``0.0`` as ``0``, ``true``, ``null``, anything else compact JSON."""
    if isinstance(value, str):
        return value
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


class _Answer:
    """One answer, its body parsed as JSON at most once."""

    def __init__(self, status: int, headers: dict[str, str], body: str, truncated: bool) -> None:
        self.status = status
        self.headers = {k.lower(): v for k, v in headers.items()}
        self._body = body
        self._truncated = truncated
        self._doc: Any = None
        self._parsed = False

    def _json(self) -> Any:
        if not self._parsed:
            self._parsed = True
            self._doc = _MISSING
            if self._body.strip() and not self._truncated:
                with contextlib.suppress(ValueError):
                    self._doc = json.loads(self._body)
        return self._doc

    def read(self, source: str, name: str) -> str | None:
        if source == "status":
            return str(self.status)
        if source == "header":
            return self.headers.get(name)
        doc = self._json()
        found = _MISSING if doc is _MISSING else _resolve_pointer(doc, name)
        return None if found is _MISSING else _as_text(found)


def judge(
    rules: list[ResponseRule],
    *,
    status: int,
    headers: dict[str, str],
    body: str,
    truncated: bool = False,
) -> RuleFailure | None:
    """The first rule the answer breaks, or ``None`` when every rule holds.

    ``headers`` are every response header (the reader decides what to show);
    ``body`` is the text read. A truncated body is not parsed: its JSON fields
    count as missing.
    """
    answer = _Answer(status, headers, body, truncated)
    for rule in rules:
        value = answer.read(rule.source, rule.name)
        if value is None:
            if rule.missing == "ok":
                continue
        elif value in rule.ok_values:
            continue
        message = answer.read(rule.message.source, rule.message.name) if rule.message else None
        return RuleFailure(
            rule=rule,
            value=None if value is None else value[:REPORTED_VALUE_MAX],
            message=message[:REPORTED_VALUE_MAX] if message else None,
        )
    return None


__all__ = [
    "MAX_DIAGNOSTIC_HEADERS",
    "MAX_RULES",
    "SENSITIVE_HEADERS",
    "HttpApiResponse",
    "ResponseField",
    "ResponseRule",
    "RuleFailure",
    "judge",
    "rule_headers",
]
