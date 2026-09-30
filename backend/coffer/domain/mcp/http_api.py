"""The HTTP API transport: a custom-tool group and the tools it holds.

Spec mcp-gateway "Serve an HTTP API as a group of custom tools". A group is an
``mcp_server`` whose ``transport`` is :class:`HttpApiTransport`; the gateway
answers ``tools/list`` from :attr:`HttpApiTransport.tools` and makes each
tool's HTTP request itself (``infrastructure/mcp/http_api_client.py``).

The one secret a group may carry is the value of its auth header. It is cited
the way the other transports cite theirs — ``credential_refs`` maps the slot
(the header's name) to the ref — so every mechanism that walks credential refs
(the missing-credential probe, the attention source, the secret boundary's
destinations) covers a group unchanged. A tool's per-agent reach override is
not here: reach is machine-local and this config travels with sync, so the
overrides live in their own table (design add-http-custom-tools §2).

Pure: Pydantic and the standard library only.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

from coffer.domain.mcp.http_api_render import holes_in, template_holes

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
HTTP_METHODS: tuple[str, ...] = ("GET", "POST", "PUT", "PATCH", "DELETE")

#: A tool's name: what follows ``<group>__`` in the name an agent sees.
TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
#: An HTTP header name (RFC 9110 token).
_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,128}$")

#: Static values that look like secrets are refused, as on the other transports.
_SECRET_PATTERNS = (
    re.compile(r"^Bearer\s+\S"),
    re.compile(r"^(ghp_|gho_|github_pat_|sk-|xox[abp]-)"),
    re.compile(r"^eyJ[A-Za-z0-9_-]{20,}"),
)


def _check_headers(values: dict[str, str], *, allow_holes: bool) -> dict[str, str]:
    for name, value in values.items():
        if not _HEADER_NAME_RE.match(name):
            raise ValueError(f"{name!r} is not a valid header name")
        if "\n" in value or "\r" in value:
            raise ValueError(f"header {name!r} holds a line break")
        if not allow_holes and holes_in(value):
            raise ValueError(f"group header {name!r} may not hold an argument hole")
        if any(p.search(value) for p in _SECRET_PATTERNS):
            raise ValueError(
                f"static value for header {name!r} looks like a secret; bind a stored "
                "secret to the group's auth header instead"
            )
    return values


def default_changes_data(method: str) -> bool:
    """Spec mcp-gateway "Annotate every tool with whether it changes data"."""
    return method != "GET"


class HttpApiTool(BaseModel):
    """One HTTP request an agent can ask the gateway to make."""

    name: str
    description: str = Field(default="", max_length=4000)
    method: HttpMethod = "GET"
    #: Relative to the group's base URL; ``{argument}`` holes in the path or
    #: the query: ``/invoices/{id}?status={status}``.
    path: str = Field(min_length=1, max_length=2000)
    headers: dict[str, str] = Field(default_factory=dict)
    #: JSON text with ``{argument}`` holes; ``None`` sends the unused arguments
    #: as a JSON object for POST, PUT and PATCH.
    body_template: str | None = Field(default=None, max_length=100_000)
    input_schema: dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}}
    )
    enabled: bool = True
    #: ``None`` follows the method (on for every method but GET).
    changes_data: bool | None = None
    #: ``"<METHOD> <path>"`` of the OpenAPI operation this tool was imported from.
    operation: str | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not TOOL_NAME_RE.match(v):
            raise ValueError(
                f"tool name {v!r} must be 1-40 letters, digits, '_' or '-', "
                "starting with a letter or digit"
            )
        if "__" in v:
            raise ValueError(f"tool name {v!r} may not contain '__'")
        return v

    @field_validator("path")
    @classmethod
    def _path(cls, v: str) -> str:
        if not v.startswith("/") or v.startswith("//") or "://" in v:
            raise ValueError(f"path {v!r} must be a path starting with a single '/'")
        if any(c in v for c in (" ", "\n", "\r", "#")):
            raise ValueError(f"path {v!r} may not hold spaces, line breaks or '#'")
        return v

    @field_validator("headers")
    @classmethod
    def _headers(cls, v: dict[str, str]) -> dict[str, str]:
        return _check_headers(v, allow_holes=True)

    @field_validator("input_schema")
    @classmethod
    def _schema(cls, v: dict[str, Any]) -> dict[str, Any]:
        if v.get("type", "object") != "object":
            raise ValueError("the argument schema must be a JSON Schema object")
        props = v.get("properties", {})
        if not isinstance(props, dict):
            raise ValueError("the argument schema's properties must be an object")
        required = v.get("required", [])
        if not isinstance(required, list) or any(r not in props for r in required):
            raise ValueError("every required argument must be declared in properties")
        return {**v, "type": "object", "properties": props}

    @model_validator(mode="after")
    def _holes_are_declared(self) -> HttpApiTool:
        declared = set(self.input_schema.get("properties", {}))
        used = template_holes(self.path, self.headers, self.body_template)
        missing = sorted(used - declared)
        if missing:
            raise ValueError(
                "argument(s) " + ", ".join(repr(m) for m in missing) + " are used in the "
                "request but not declared in the argument schema"
            )
        return self

    @property
    def effective_changes_data(self) -> bool:
        if self.changes_data is None:
            return default_changes_data(self.method)
        return self.changes_data

    @property
    def request_label(self) -> str:
        return f"{self.method} {self.path}"


class OpenApiSource(BaseModel):
    """Where a group's tools were imported from, for re-import."""

    kind: Literal["url", "file"]
    location: str = Field(min_length=1, max_length=2000)
    title: str | None = None
    version: str | None = None
    fetched_at: datetime
    #: Operation keys (``"<METHOD> <path>"``) seen and left out.
    skipped: list[str] = Field(default_factory=list)


class HttpApiTransport(BaseModel):
    """A custom-tool group: one base URL, one auth, many requests."""

    type: Literal["http_api"] = "http_api"
    base_url: HttpUrl
    headers: dict[str, str] = Field(default_factory=dict)
    auth_header: str | None = None
    auth_prefix: str = Field(default="", max_length=64)
    #: ``{auth_header: ref}`` — the one secret, when the auth header is bound.
    credential_refs: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    source: OpenApiSource | None = None
    tools: list[HttpApiTool] = Field(default_factory=list)

    @field_validator("base_url")
    @classmethod
    def _scheme(cls, v: HttpUrl) -> HttpUrl:
        if v.scheme not in ("http", "https"):
            raise ValueError("the base URL must be http or https")
        if v.query or v.fragment:
            raise ValueError("the base URL may not carry a query or a fragment")
        return v

    @field_validator("headers")
    @classmethod
    def _headers(cls, v: dict[str, str]) -> dict[str, str]:
        return _check_headers(v, allow_holes=False)

    @field_validator("auth_header")
    @classmethod
    def _auth_header(cls, v: str | None) -> str | None:
        if v is not None and not _HEADER_NAME_RE.match(v):
            raise ValueError(f"{v!r} is not a valid header name")
        return v

    @model_validator(mode="after")
    def _consistent(self) -> HttpApiTransport:
        names = [t.name for t in self.tools]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError("tool names must be unique in a group: " + ", ".join(dupes))
        if self.credential_refs and (
            self.auth_header is None or set(self.credential_refs) != {self.auth_header}
        ):
            raise ValueError("a group's only secret is its auth header's value")
        return self

    def tool(self, name: str) -> HttpApiTool | None:
        return next((t for t in self.tools if t.name == name), None)

    @property
    def secret_ref(self) -> str | None:
        return self.credential_refs.get(self.auth_header or "") if self.auth_header else None


def http_api_target(transport: HttpApiTransport) -> str:
    """What receives a group's secret, for the secret boundary: its base URL."""
    return f"http_api {transport.base_url}"


__all__ = [
    "HTTP_METHODS",
    "TOOL_NAME_RE",
    "HttpApiTool",
    "HttpApiTransport",
    "HttpMethod",
    "OpenApiSource",
    "default_changes_data",
    "http_api_target",
]
