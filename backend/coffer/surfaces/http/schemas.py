"""Pydantic API schemas (kind-agnostic).

Wire-compatible with specs/001-mcp-gateway/contracts/api.openapi.yaml.
MCP-kind-specific schemas live in surfaces/http/mcp/schemas.py (Phase 3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# --- Error envelope ---


class ErrorDetail(BaseModel):
    code: str = Field(examples=["RESOURCE_NOT_FOUND"])
    message: str = Field(examples=["resource not found: mcp_server:filesystem"])
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


# --- Resources (kind-agnostic) ---


class ResourceOut(BaseModel):
    ref: str = Field(examples=["mcp_server:filesystem"])
    kind: str
    name: str
    description: str | None = None
    config: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ResourceCreate(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.\-]+$")
    description: str | None = None
    config: dict[str, Any]


class ResourceUpdate(BaseModel):
    description: str | None = None
    config: dict[str, Any] | None = None


class ResourceListOut(BaseModel):
    resources: list[ResourceOut]


# --- Audit ---


class AuditEntryOut(BaseModel):
    id: int
    timestamp: datetime
    event_type: str
    resource_kind: str | None = None
    resource_name: str | None = None
    actor: str
    details: dict[str, Any] | None = None


class AuditListOut(BaseModel):
    entries: list[AuditEntryOut]


# --- Retention ---


class RetentionPolicyOut(BaseModel):
    table_name: str
    display_name: str
    description: str
    default_retention_days: int | None
    retention_days: int | None
    last_pruned_at: datetime | None = None
    last_pruned_rows: int


class RetentionPolicyListOut(BaseModel):
    policies: list[RetentionPolicyOut]


class RetentionPolicyUpdate(BaseModel):
    retention_days: int | None = Field(
        default=None,
        ge=1,
        le=3650,
        description="Null = keep forever; 1..3650 days otherwise.",
    )


class PruneResultOut(BaseModel):
    tables: dict[str, int]


# --- Daemon ---


class UpstreamSummary(BaseModel):
    registered: int
    enabled: int
    healthy: int
    unhealthy: int


class DaemonStatusOut(BaseModel):
    status: Literal["starting", "ready", "draining"]
    version: str
    started_at: datetime
    port: int
    upstream_summary: UpstreamSummary | None = None


class BackupResultOut(BaseModel):
    path: str
    size_bytes: int


class TokenRotationOut(BaseModel):
    token: str = Field(description="New token; clients must re-read daemon.json")


# --- MCP capability views ---


class MCPToolView(BaseModel):
    prefixed_name: str = Field(examples=["filesystem__read_file"])
    original_name: str = Field(examples=["read_file"])
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    enabled: bool


class MCPResourceView(BaseModel):
    prefixed_uri: str
    original_uri: str
    name: str | None = None
    description: str | None = None
    mime_type: str | None = None
    enabled: bool


class _MCPPromptArgument(BaseModel):
    name: str
    description: str | None = None
    required: bool = False


class MCPPromptView(BaseModel):
    prefixed_name: str
    original_name: str
    description: str | None = None
    arguments: list[_MCPPromptArgument] = Field(default_factory=list)
    enabled: bool


class CapabilityListOut(BaseModel):
    server_name: str
    tools: list[MCPToolView]
    resources: list[MCPResourceView]
    prompts: list[MCPPromptView]
    fetched_at: datetime
    from_cache: bool = False


class McpTestResultOut(BaseModel):
    ok: bool
    latency_ms: int
    protocol_version: str | None = None
    server_capabilities: dict[str, Any] | None = None
    error_message: str | None = None


class InvocationOut(BaseModel):
    timestamp: datetime
    capability_type: str = Field(pattern="^(tool|resource|prompt)$")
    capability_key: str
    duration_ms: int
    status: str
    error_message: str | None = None
    session_id: str | None = None


class InvocationListOut(BaseModel):
    invocations: list[InvocationOut]


# --- Credentials ---


class CredentialSetIn(BaseModel):
    """Request body for storing a secret in the credential store.

    Secrets are Fernet-encrypted into the coffer DB; only ciphertext is
    persisted; audit rows carry the ref only.
    """

    ref: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$",
        description=(
            "Reference key the secret is stored under. Slash-separated "
            "segments are allowed (e.g. channel/tg/bot-token)."
        ),
    )
    value: str = Field(
        min_length=1,
        max_length=8192,
        description="The secret value.",
    )


class CredentialExistsOut(BaseModel):
    """Presence-only response — never carries the secret value."""

    present: bool = Field(description="Whether a secret is stored under the ref.")


class CredentialGetOut(BaseModel):
    """Secret-value response for an explicit read from the credential store."""

    value: str = Field(description="The stored secret value.")


# --- MCP capability enable/disable body ---


class CapabilityKeyBody(BaseModel):
    """Request body for capability enable/disable routes.

    Carries the capability_key (tool name, resource URI, or prompt name) in
    the body rather than the URL path so that keys containing '/' (e.g.
    resource URIs like ``file:///path/to/x``) are routed correctly.
    """

    capability_key: str = Field(min_length=1, max_length=2048)


# --- MCP server status ---


class McpServerStatusOut(BaseModel):
    """Cheap per-server status, derived from persisted state (no spawn)."""

    status: Literal["healthy", "failing", "unknown"]


# --- Settings ---


class CredentialSettingsOut(BaseModel):
    """Where the credential-store master key currently lives."""

    master_key_storage: Literal["file", "keychain"] = Field(
        description="file = ~/.coffer/master.key (default); keychain = OS keychain entry."
    )


class CredentialSettingsIn(BaseModel):
    """Request body to relocate the master key."""

    master_key_storage: Literal["file", "keychain"]


# --- Embedding config (global) ---


class EmbeddingConfigOut(BaseModel):
    enabled: bool
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    credential_ref: str | None = None
    dimensions: int
    default_chunk_size: int = 512
    default_chunk_overlap: int = 64
    updated_at: datetime | None = None


class EmbeddingConfigUpdate(BaseModel):
    enabled: bool = False
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    credential_ref: str | None = None
    dimensions: int = Field(default=768, ge=1, le=8192)
    default_chunk_size: int = Field(default=512, ge=64, le=2048)
    default_chunk_overlap: int = Field(default=64, ge=0)
