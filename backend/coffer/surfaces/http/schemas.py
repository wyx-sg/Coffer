"""Pydantic API schemas (kind-agnostic).

Wire-compatible with openspec/specs/mcp-gateway/contracts/api.openapi.yaml.
MCP-kind-specific schemas live in surfaces/http/mcp/schemas.py (Phase 3).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from coffer.domain.resource import FREE_NAME_MAX_LEN
from coffer.domain.scope import Scope

# --- Error envelope ---


class ErrorDetail(BaseModel):
    code: str = Field(examples=["RESOURCE_NOT_FOUND"])
    message: str = Field(examples=["resource not found: mcp_server:filesystem"])
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail


# --- Resources (kind-agnostic) ---


class ScopeIn(BaseModel):
    """A resource's activation scope as a request writes it: one allow-list of
    agents (ADR per-agent-resource-scope). ``null`` or absent means
    unrestricted; an empty list is refused (switch the resource off instead).

    Extra keys are REFUSED rather than ignored, which is the unusual choice and
    the deliberate one. This model used to carry a second axis, ``machines``,
    and a client that still sends it — a browser tab left open across the
    upgrade — means "only on that machine". Ignoring the key would store what
    is left, ``agents: null``, and that reads as *every agent, everywhere*: the
    request would silently widen the very restriction it was trying to write.
    A 422 tells the caller its request was not understood, which is the only
    honest answer.
    """

    model_config = ConfigDict(extra="forbid")

    #: Agent resource UIDS, not names. A name-shaped example here would teach
    #: the wrong vocabulary to everyone reading the generated client.
    agents: list[str] | None = Field(default=None, examples=[["9f2c1a7b4e8d4c1fa0b3d5e6f7081920"]])

    def to_domain(self) -> Scope:
        return Scope(agents=self.agents)


class ScopeOut(BaseModel):
    """A resource's activation scope as a response carries it. ``agents`` is
    always present: ``null`` means unrestricted; never an empty list."""

    agents: list[str] | None = Field(examples=[["9f2c1a7b4e8d4c1fa0b3d5e6f7081920"]])

    @classmethod
    def of(cls, scope: Scope | None) -> ScopeOut | None:
        """The wire shape of a stored scope; null stays null (unscoped)."""
        return None if scope is None else cls(agents=scope.agents)


class DeliveryResultOut(BaseModel):
    """What delivering a reach change did for one agent."""

    agent_uid: str
    agent_name: str
    ok: bool
    reason: str | None = None  # why nothing was linked there; null when ok


class ResourceOut(BaseModel):
    #: The identity. Immutable, opaque, and the same value on every machine
    #: holding this resource — every route that addresses one takes this.
    uid: str = Field(examples=["9f2c1a7b4e8d4c1fa0b3d5e6f7081920"])
    kind: str
    #: A label, unique within ``kind``. Editable through PATCH unless the kind
    #: declares its name fixed (``mcp_server``, ``skill``): 409 NAME_IMMUTABLE.
    #: Free display text for a provider or a channel; a slug for the rest.
    name: str
    description: str | None = None
    config: dict[str, Any]
    # Framework-level activation scope (ADR per-agent-resource-scope). None =
    # unscoped (active for every agent); only kinds whose Kind.supports_scope
    # is True may set it. See GET/PUT .../scope below.
    scope: ScopeOut | None = None
    enabled: bool
    #: Per agent, whether a reach change was delivered: only skills' PUT .../scope fills it.
    delivery: list[DeliveryResultOut] | None = None
    #: ``Kind.toggleable``: False (knowledge, memory) means enable/disable is
    #: refused with RESOURCE_NOT_TOGGLEABLE, so a surface leaves the switch out.
    toggleable: bool
    #: A stdio MCP server whose environment carries a secret: readable by any
    #: other process of this user on this Mac (spec mcp-gateway "Mark a stdio
    #: server whose environment carries a secret"). False for every other row.
    secrets_readable_by_local_processes: bool = False
    created_at: datetime
    updated_at: datetime


class ResourceCreate(BaseModel):
    kind: str
    #: Checked against the kind's rule by the service: free text up to 80
    #: characters for a provider or a channel, a slug for the rest.
    name: str = Field(min_length=1, max_length=FREE_NAME_MAX_LEN)
    description: str | None = None
    config: dict[str, Any]


class ResourceUpdate(BaseModel):
    #: Renaming is a field. Absent leaves the label alone; a name taken within
    #: the kind is a 409, as is any change to a fixed name (NAME_IMMUTABLE).
    name: str | None = Field(default=None, min_length=1, max_length=FREE_NAME_MAX_LEN)
    description: str | None = None
    config: dict[str, Any] | None = None


class ResourceListOut(BaseModel):
    resources: list[ResourceOut]


class ResourceScopeOut(BaseModel):
    """GET .../scope response: the current scope plus whether this kind
    supports scope at all (False means any non-null write is a 422)."""

    scope: ScopeOut | None = None
    supports_scope: bool = False


class ResourceScopeUpdate(BaseModel):
    """PUT .../scope request body: which agents this resource is active for.

    ``scope: null`` clears back to unscoped — every agent. A list restricts to
    exactly those agents and must name at least one: ``{"agents": []}`` is
    refused with 422 ``SCOPE_INVALID`` (switch the resource off to reach nobody).

    Scope is set per machine and does not sync: every machine holding this
    vault decides for itself which of its agents a resource activates for."""

    scope: ScopeIn | None = None


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


class RetentionPreviewOut(BaseModel):
    """What shortening one policy's window would delete, counted and not run."""

    table_name: str
    days: int
    #: Every row the table holds now.
    total_rows: int
    #: The rows older than ``days`` — deleted at the next cleanup once saved.
    rows_to_delete: int


class RetentionPolicyUpdate(BaseModel):
    retention_days: int | None = Field(
        default=None,
        ge=1,
        le=3650,
        description="Null = keep forever; 1..3650 days otherwise.",
    )


class PruneRequestIn(BaseModel):
    """``POST /retention/prune`` body; the whole body is optional."""

    #: The one table to prune; absent or null prunes every registered table.
    table_name: str | None = None


class PruneResultOut(BaseModel):
    tables: dict[str, int]


# --- Daemon ---
#
# In ``daemon_schemas.py``, re-exported here so every existing
# ``from ...schemas import DaemonStatusOut`` keeps resolving.

from coffer.surfaces.http.daemon_schemas import DaemonLogListOut as DaemonLogListOut  # noqa: E402
from coffer.surfaces.http.daemon_schemas import (  # noqa: E402
    DaemonLogRecordOut as DaemonLogRecordOut,
)
from coffer.surfaces.http.daemon_schemas import DaemonResidencyIn as DaemonResidencyIn  # noqa: E402
from coffer.surfaces.http.daemon_schemas import (  # noqa: E402
    DaemonResidencyOut as DaemonResidencyOut,
)
from coffer.surfaces.http.daemon_schemas import DaemonStatusOut as DaemonStatusOut  # noqa: E402
from coffer.surfaces.http.daemon_schemas import TokenRotationOut as TokenRotationOut  # noqa: E402
from coffer.surfaces.http.daemon_schemas import UpstreamSummary as UpstreamSummary  # noqa: E402

# --- MCP capability views ---


class MCPToolView(BaseModel):
    prefixed_name: str = Field(examples=["filesystem__read_file"])
    original_name: str = Field(examples=["read_file"])
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    enabled: bool
    #: len("mcp__coffer__<prefixed_name>"); over 64 is past the provider limit.
    client_name_length: int


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
    client_name_length: int  # as on a tool


class CapabilityListOut(BaseModel):
    server_name: str
    tools: list[MCPToolView]
    resources: list[MCPResourceView]
    prompts: list[MCPPromptView]
    fetched_at: datetime
    from_cache: bool = False


# --- MCP capability enable/disable body ---


class CapabilityKeyBody(BaseModel):
    """Request body for capability enable/disable routes.

    Carries the capability_key (tool name, resource URI, or prompt name) in
    the body rather than the URL path so that keys containing '/' (e.g.
    resource URIs like ``file:///path/to/x``) are routed correctly.
    """

    capability_key: str = Field(min_length=1, max_length=2048)


# --- Settings ---


class SecretSettingsOut(BaseModel):
    """Where the secret-store master key currently lives."""

    master_key_storage: Literal["file", "keychain", "keychain_access_group"] = Field(
        description=(
            "file = ~/.coffer/master.key (development default); keychain = OS keychain "
            "entry (development opt-in); keychain_access_group = the signed release's "
            "Keychain access group, the only place a release keeps it."
        )
    )


class SecretSettingsIn(BaseModel):
    """Request body to relocate the master key."""

    master_key_storage: Literal["file", "keychain"]
