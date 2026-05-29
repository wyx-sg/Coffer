"""MCP server configuration value objects.

`MCPServerConfig` is what `Resource.config` holds when `kind == "mcp_server"`.
Stdio + HTTP transports as a Pydantic discriminated union.
"""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, field_validator

# Patterns that look like secrets — if a static env/header value matches,
# reject it; secrets must go through `credential_refs` so they live in
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
                    f"static value for {k!r} looks like a secret; "
                    f"move it into credential_refs instead"
                )
    return values


class StdioTransport(BaseModel):
    type: Literal["stdio"] = "stdio"
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    credential_refs: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None

    @field_validator("env")
    @classmethod
    def _no_secrets_in_env(cls, v: dict[str, str]) -> dict[str, str]:
        return _reject_secret_values(v)


class HttpTransport(BaseModel):
    type: Literal["http"] = "http"
    url: HttpUrl
    headers: dict[str, str] = Field(default_factory=dict)
    credential_refs: dict[str, str] = Field(default_factory=dict)

    @field_validator("headers")
    @classmethod
    def _no_secrets_in_headers(cls, v: dict[str, str]) -> dict[str, str]:
        return _reject_secret_values(v)


Transport = Annotated[
    StdioTransport | HttpTransport,
    Field(discriminator="type"),
]


class MCPServerConfig(BaseModel):
    transport: Transport
    auto_enable_new_capabilities: bool = True
    spawn_timeout_seconds: int = Field(default=30, ge=5, le=120)
    request_timeout_seconds: int = Field(default=120, ge=5, le=1800)
    idle_timeout_seconds: int = Field(default=600, ge=60, le=86400)
