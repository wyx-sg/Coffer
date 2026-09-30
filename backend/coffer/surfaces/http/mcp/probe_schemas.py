"""Wire models for testing an MCP server — a registered one or an unsaved config.

Spec mcp-gateway "Test an unsaved server config before adding it" and "Test a
registered server on demand". Both routes answer :class:`McpTestResultOut`, so
the Add dialog and the server page read one shape. No field carries a secret
value: typed secrets are redacted from ``stderr_tail`` and ``error_message``
before the result is built.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, HttpUrl

from coffer.domain.mcp.probe import ProbeResult
from coffer.domain.mcp.server_config import HttpTransport, StdioTransport

McpTestErrorCode = Literal[
    "url_refused",
    "spawn_failed",
    "exited",
    "timeout",
    "initialize_failed",
    "connect_failed",
    "stored_secret_not_released",
    "unsupported_transport",
]


class McpTestToolOut(BaseModel):
    name: str
    description: str | None = None


class McpTestResultOut(BaseModel):
    """What one test found."""

    ok: bool
    latency_ms: int = Field(description="From the start of the test to its outcome.")
    protocol_version: str | None = None
    server_capabilities: dict[str, Any] | None = None
    error_message: str | None = Field(
        default=None, description="One readable sentence; typed secret values redacted."
    )
    error_code: McpTestErrorCode | None = Field(
        default=None,
        description=(
            "Why the test failed: url_refused (a typed URL resolves to a loopback, "
            "private or link-local host), spawn_failed (the command or working "
            "directory does not exist), exited (the process exited; see exit_code), "
            "timeout (the time limit), initialize_failed (MCP initialize or "
            "tools/list failed), connect_failed (the URL could not be reached), "
            "stored_secret_not_released (the config cites a stored secret, released "
            "only to a registered server), unsupported_transport."
        ),
    )
    tools: list[McpTestToolOut] = Field(default_factory=list)
    tool_count: int = 0
    resource_count: int | None = Field(
        default=None, description="Null when the server declares no resources."
    )
    prompt_count: int | None = Field(
        default=None, description="Null when the server declares no prompts."
    )
    exit_code: int | None = Field(default=None, description="Set when error_code is exited.")
    stderr_tail: list[str] = Field(
        default_factory=list,
        description="The newest (at most 20) lines the process printed on stderr, redacted.",
    )
    unreleased_secret_keys: list[str] = Field(
        default_factory=list,
        description="With stored_secret_not_released: the keys whose stored secret was cited.",
    )


class McpTestStdioIn(BaseModel):
    """A stdio server as the Add form holds it."""

    type: Literal["stdio"] = "stdio"
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: str | None = None
    secret_refs: dict[str, str] = Field(
        default_factory=dict, description="KEY → a stored secret picked for this variable."
    )

    def to_transport(self) -> StdioTransport:
        return StdioTransport(
            command=self.command,
            args=self.args,
            env=self.env,
            cwd=self.cwd,
            credential_refs=self.secret_refs,
        )


class McpTestHttpIn(BaseModel):
    """A Streamable HTTP server as the Add form holds it."""

    type: Literal["http"] = "http"
    url: HttpUrl
    headers: dict[str, str] = Field(default_factory=dict)
    secret_refs: dict[str, str] = Field(
        default_factory=dict, description="Header → a stored secret picked for it."
    )

    def to_transport(self) -> HttpTransport:
        return HttpTransport(url=self.url, headers=self.headers, credential_refs=self.secret_refs)


class McpConfigTestIn(BaseModel):
    """A config as the Add form would register it, tested without saving it."""

    name: str | None = Field(
        default=None, max_length=64, description="For the diagnostics only; nothing is named."
    )
    transport: Annotated[McpTestStdioIn | McpTestHttpIn, Field(discriminator="type")]
    spawn_timeout_seconds: int = Field(default=30, ge=5, le=120)
    request_timeout_seconds: int = Field(default=120, ge=5, le=1800)
    secret_values: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Values typed into the form's Secret rows, KEY → value: set in the "
            "environment (stdio) or as headers (HTTP) for this test only. Never "
            "stored, logged or echoed."
        ),
        json_schema_extra={"writeOnly": True},
    )


def result_out(result: ProbeResult, **extra: Any) -> McpTestResultOut:
    return McpTestResultOut(
        ok=result.ok,
        latency_ms=result.latency_ms,
        protocol_version=result.protocol_version,
        server_capabilities=dict(result.server_capabilities)
        if result.server_capabilities is not None
        else None,
        error_message=result.error_message,
        error_code=result.error_code,
        tools=[McpTestToolOut(name=t.name, description=t.description) for t in result.tools],
        tool_count=result.tool_count,
        resource_count=result.resource_count,
        prompt_count=result.prompt_count,
        exit_code=result.exit_code,
        stderr_tail=list(result.stderr_tail),
        **extra,
    )


__all__ = [
    "McpConfigTestIn",
    "McpTestErrorCode",
    "McpTestResultOut",
    "McpTestToolOut",
    "result_out",
]
