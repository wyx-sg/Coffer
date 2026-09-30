"""MCP server configuration value objects.

`MCPServerConfig` is what `Resource.config` holds when `kind == "mcp_server"`.
Stdio, HTTP and HTTP API transports as a Pydantic discriminated union. The
third, ``http_api``, is a custom-tool group whose tools are HTTP requests the
gateway makes itself (``coffer.domain.mcp.http_api``).
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from coffer.domain.mcp.http_api import HttpApiTransport

# Patterns that look like secrets — if a static env/header value matches,
# reject it; secrets must go through `secret_refs` so they live in
# the keychain rather than the config DB.
_SECRET_PATTERNS = [
    re.compile(r"^Bearer\s+"),
    re.compile(r"^ghp_"),
    re.compile(r"^gho_"),
    re.compile(r"^github_pat_"),
    re.compile(r"^sk-"),
    re.compile(r"^xox[abp]-"),
    re.compile(r"^eyJ[A-Za-z0-9_-]{20,}"),  # JWT prefix
]


def _reject_secret_values(values: dict[str, str]) -> dict[str, str]:
    for k, v in values.items():
        for pat in _SECRET_PATTERNS:
            if pat.search(v):
                raise ValueError(
                    f"static value for {k!r} looks like a secret; move it into secret_refs instead"
                )
    return values


class StdioTransport(BaseModel):
    type: Literal["stdio"] = "stdio"
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    secret_refs: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None

    @field_validator("env")
    @classmethod
    def _no_secrets_in_env(cls, v: dict[str, str]) -> dict[str, str]:
        return _reject_secret_values(v)


class HttpTransport(BaseModel):
    type: Literal["http"] = "http"
    url: HttpUrl
    headers: dict[str, str] = Field(default_factory=dict)
    secret_refs: dict[str, str] = Field(default_factory=dict)

    @field_validator("headers")
    @classmethod
    def _no_secrets_in_headers(cls, v: dict[str, str]) -> dict[str, str]:
        return _reject_secret_values(v)


Transport = Annotated[
    StdioTransport | HttpTransport | HttpApiTransport,
    Field(discriminator="type"),
]


#: Every transport the gateway can open a connection for.
AnyTransport = StdioTransport | HttpTransport | HttpApiTransport


class MCPServerConfig(BaseModel):
    # A key the model does not declare is refused rather than dropped, so a
    # retired field cannot linger in a stored config unnoticed.
    model_config = ConfigDict(extra="forbid")

    transport: Transport
    spawn_timeout_seconds: int = Field(default=30, ge=5, le=120)
    request_timeout_seconds: int = Field(default=120, ge=5, le=1800)
