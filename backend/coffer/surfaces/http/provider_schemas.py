"""Request / response schemas for ``/api/v1/providers`` (spec 011).

``ProviderOut`` NEVER carries the secret — only its ``credential_ref``.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from coffer.domain.provider.config import WireApi, WireFormat


class ProviderCreate(BaseModel):
    """Create an LLM connection. For ``anthropic`` / ``openai`` supply EXACTLY
    one of ``secret_value`` / ``credential_ref``; an ``ollama`` connection has
    no key, so supply neither."""

    name: str = Field(min_length=1, max_length=64)
    wire_format: WireFormat
    base_url: str = Field(min_length=1)
    model: str = Field(min_length=1)
    fast_model: str | None = None
    # Default ``responses`` — codex-cli 0.130 rejects ``wire_api = "chat"``.
    wire_api: WireApi = WireApi.RESPONSES
    credential_ref: str | None = None
    secret_value: str | None = Field(default=None, max_length=8192)
    description: str | None = None


class ProviderPatch(BaseModel):
    """Partial update. ``wire_format`` / ``credential_ref`` are immutable."""

    base_url: str | None = None
    model: str | None = None
    fast_model: str | None = None
    wire_api: WireApi | None = None
    secret_value: str | None = Field(default=None, max_length=8192)
    description: str | None = None


class ProviderOut(BaseModel):
    """An LLM connection as returned by the API (no secret).

    ``credential_ref`` is ``None`` for ``ollama`` connections (no key).
    ``internal_default`` marks the connection Coffer's internal engine uses
    (at most one globally); ``is_active`` marks the one projected to its wire's
    agent — a connection may be both.
    """

    name: str
    wire_format: WireFormat
    base_url: str
    credential_ref: str | None
    model: str
    fast_model: str | None
    wire_api: WireApi
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
    wire_format: WireFormat
    projected: list[str]
    skipped: list[str]


class ActiveKeyOut(BaseModel):
    """The decrypted API key of the active profile for a wire format.

    Served over the local token-protected daemon API for Claude Code's
    ``apiKeyHelper`` (same exposure as the existing credential-GET route). Not
    audited — ``apiKeyHelper`` polls it frequently.
    """

    value: str
