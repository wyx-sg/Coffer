"""The HTTP API transport: a custom-tool group and the tools it holds.

Spec mcp-gateway "Serve an HTTP API as a group of custom tools". A group is an
``mcp_server`` whose ``transport`` is :class:`HttpApiTransport`; the gateway
answers ``tools/list`` from :attr:`HttpApiTransport.tools` and makes each
tool's HTTP request itself (``infrastructure/mcp/http_api_client.py``).

A group keeps one set of tools and one or more environments
(``http_api_environment``): where the tools are sent, each with its base URL,
header rows (a plain value, or a stored secret holding the credential alone
behind an optional scheme), variables, switch and timeout. The group's
``secret_refs`` is DERIVED from its environments — each environment's slots
(``<key>:<header>``, the bare header for a lifted group) mapped to their refs
— so every mechanism that walks secret refs (the missing-secret probe, the
citation index, the attention sources, delete-time release) covers every
environment unchanged. A tool has no reach of its own; it follows the group's.

Pure: Pydantic and the standard library only.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from coffer.domain.mcp.http_api_environment import (
    ENVIRONMENT_ARG,
    HttpApiEnvironment,
    env_vars_in,
    lift_legacy,
)
from coffer.domain.mcp.http_api_headers import check_headers
from coffer.domain.mcp.http_api_render import template_holes
from coffer.domain.mcp.json_schema_check import InvalidSchema, check_schema

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
HTTP_METHODS: tuple[str, ...] = ("GET", "POST", "PUT", "PATCH", "DELETE")

#: A tool's name: what follows ``<group>__`` in the name an agent sees.
TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
#: How much of one operation's spec text a tool keeps.
SOURCE_TEXT_LIMIT = 20_000


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
    #: The operation's text in the spec it was imported from, so a re-import
    #: can show what changed in it.
    source_text: str | None = Field(default=None, max_length=SOURCE_TEXT_LIMIT)

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
        return check_headers(v, allow_holes=True)

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
        if ENVIRONMENT_ARG in props:
            raise ValueError(
                f"{ENVIRONMENT_ARG!r} is reserved: Coffer adds it to choose the environment"
            )
        out = {**v, "type": "object", "properties": props}
        try:
            check_schema(out)
        except InvalidSchema as e:
            raise ValueError(f"the argument schema is not valid JSON Schema: {e}") from e
        return out

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
    def env_vars(self) -> set[str]:
        """Every ``{env:NAME}`` the tool's request names."""
        names = env_vars_in(self.path)
        for value in self.headers.values():
            names |= env_vars_in(value)
        if self.body_template:
            names |= env_vars_in(self.body_template)
        return names

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
    """A custom-tool group: one set of tools, sent to one of its environments."""

    type: Literal["http_api"] = "http_api"
    environments: list[HttpApiEnvironment] = Field(min_length=1)
    #: The group's timeout; an environment may set its own.
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    source: OpenApiSource | None = None
    tools: list[HttpApiTool] = Field(default_factory=list)
    #: Derived from the environments on every validation: ``{slot: ref}``.
    secret_refs: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _lift(cls, data: Any) -> Any:
        """A group stored before environments reads as one ``default``."""
        return lift_legacy(data) if isinstance(data, dict) else data

    @model_validator(mode="after")
    def _consistent(self) -> HttpApiTransport:
        names = [t.name for t in self.tools]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError("tool names must be unique in a group: " + ", ".join(dupes))
        env_names = [e.name.lower() for e in self.environments]
        if len(env_names) != len(set(env_names)):
            raise ValueError("environment names must be unique in a group")
        keys = [e.key for e in self.environments]
        if len(keys) != len(set(keys)):
            raise ValueError("environment keys must be unique in a group")
        for tool in self.tools:
            for env in self.environments:
                missing = sorted(tool.env_vars - set(env.variables))
                if env.enabled and missing:
                    raise ValueError(
                        f"tool {tool.name!r} uses variable(s) {', '.join(missing)} that "
                        f"environment {env.name!r} does not define"
                    )
        self.secret_refs = {
            slot: ref for env in self.environments for slot, ref in env.slot_refs().items()
        }
        return self

    def tool(self, name: str) -> HttpApiTool | None:
        return next((t for t in self.tools if t.name == name), None)

    def environment(self, name: str) -> HttpApiEnvironment | None:
        return next((e for e in self.environments if e.name == name), None)

    def timeout_for(self, env: HttpApiEnvironment) -> int:
        return env.timeout_seconds or self.timeout_seconds


def http_api_target(env: HttpApiEnvironment) -> str:
    """What receives an environment's secret, for the secret boundary: its base URL."""
    return f"http_api {env.base_url}"


__all__ = [
    "HTTP_METHODS",
    "SOURCE_TEXT_LIMIT",
    "TOOL_NAME_RE",
    "HttpApiEnvironment",
    "HttpApiTool",
    "HttpApiTransport",
    "HttpMethod",
    "OpenApiSource",
    "default_changes_data",
    "http_api_target",
]
