"""Request / response schemas for ``/api/v1/providers`` (spec provider-switching).

``ProviderOut`` NEVER carries the secret — only its ``credential_ref``. A
connection is a credentialed endpoint ``{protocol, base_url, credential_ref}``;
the model lives apart from it (spec provider-switching E3) and is chosen at the point of use.
``models`` is the curated set the connection OFFERS to that choice — empty means
no restriction (every model the endpoint serves).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import Protocol


class ProviderCreate(BaseModel):
    """Create an LLM connection. For ``anthropic`` / ``openai`` / ``unknown``
    supply EXACTLY one of ``secret_value`` / ``credential_ref``; an ``ollama``
    connection has no key, so supply neither. ``compatible_agents`` overrides the
    wire default for which agents the connection projects into (``None`` ⇒ default).
    ``models`` curates which of the endpoint's models this connection offers
    downstream (``None`` ⇒ empty ⇒ no restriction)."""

    name: str = Field(min_length=1, max_length=64)
    protocol: Protocol
    base_url: str = Field(min_length=1)
    credential_ref: str | None = None
    secret_value: str | None = Field(default=None, max_length=8192)
    compatible_agents: list[AgentType] | None = None
    models: list[str] | None = None
    description: str | None = None


class ProviderPatch(BaseModel):
    """Partial update. ``protocol`` / ``credential_ref`` are immutable;
    ``compatible_agents`` is mutable (re-target then re-activate to re-project).
    ``models`` replaces the curated set as a whole, like ``compatible_agents``:
    ``None`` leaves it alone, ``[]`` clears the restriction."""

    base_url: str | None = None
    secret_value: str | None = Field(default=None, max_length=8192)
    compatible_agents: list[AgentType] | None = None
    models: list[str] | None = None
    description: str | None = None


class ProviderRename(BaseModel):
    """Move a connection to a new name.

    Separate from ``ProviderPatch`` because the name is the connection's
    IDENTITY, not part of its config: the vault ref it owns, its audit trail and
    the agent config it is projected into all spell the name out, so changing it
    is an operation of its own rather than another optional patch field.
    """

    new_name: str = Field(min_length=1, max_length=64)


class ProviderOut(BaseModel):
    """An LLM connection as returned by the API (no secret).

    ``credential_ref`` is ``None`` for ``ollama`` connections (no key).
    ``compatible_agents`` is the EFFECTIVE (resolved) set of agents this
    connection projects into — the explicit override or the wire default — so the
    UI can filter agents without re-deriving the default. ``models`` is the
    curated set of model ids this connection offers to every downstream picker;
    EMPTY means no restriction — the endpoint's whole catalogue. ``internal_default``
    marks the connection Coffer's internal engine uses (at most one globally);
    ``is_active`` marks the one currently projected — a connection may be both.
    """

    name: str
    protocol: Protocol
    base_url: str
    credential_ref: str | None
    compatible_agents: list[AgentType]
    models: list[str]
    is_active: bool
    internal_default: bool
    enabled: bool
    description: str | None
    created_at: datetime
    updated_at: datetime


class ProviderListOut(BaseModel):
    providers: list[ProviderOut]


class ActivateOut(BaseModel):
    """Result of a switch — which agents were written, which wire had none."""

    activated: str
    protocol: Protocol
    projected: list[str]
    skipped: list[str]


class DeactivateOut(BaseModel):
    """Result of switching a wire back to the agent's own built-in login."""

    protocol: Protocol
    deprojected: list[str]
    previous: str | None = None


class ActiveKeyOut(BaseModel):
    """The decrypted API key of the active profile for a wire format.

    Served over the local token-protected daemon API for Claude Code's
    ``apiKeyHelper`` (same exposure as the existing credential-GET route). Not
    audited — ``apiKeyHelper`` polls it frequently.
    """

    value: str


# ---------------------------------------------------------------------------
# Introspection: probe a connection, list what it serves.
#
# These moved here from the chat page's schema module when that page was
# removed. They were never chat schemas — the connection editor and the
# embedding settings are what post to /api/v1/models.
# ---------------------------------------------------------------------------


class TestConnectionIn(BaseModel):
    provider: str
    model: str
    credential_ref: str | None = None
    secret_value: str | None = None  # inline secret to test before saving
    base_url: str | None = None


class ListModelsIn(BaseModel):
    provider: str
    credential_ref: str | None = None
    secret_value: str | None = None  # inline secret to fetch before saving
    base_url: str | None = None


class DetectProtocolIn(BaseModel):
    base_url: str | None = None
    credential_ref: str | None = None
    secret_value: str | None = None  # inline secret to probe before saving


class DetectProtocolOut(BaseModel):
    protocol: str  # "anthropic" | "openai" | "ollama" | "unknown"


class TestResultOut(BaseModel):
    ok: bool
    message: str
    detail: dict[str, object] = {}


class ProviderModelsOut(BaseModel):
    models: list[str]
    message: str = ""


class EmbeddingTestIn(BaseModel):
    provider: str
    model: str
    credential_ref: str | None = None
    base_url: str | None = None
