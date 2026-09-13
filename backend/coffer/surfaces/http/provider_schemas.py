"""Request / response schemas for ``/api/v1/providers`` (spec provider-switching).

``ProviderOut`` NEVER carries the secret — only its ``credential_ref``. A
connection is a credentialed endpoint ``{protocol, base_url, credential_ref}``;
the model lives apart from it (spec provider-switching E3) and is chosen at the point of use.
``models`` is the curated set the connection OFFERS to that choice — empty means
no restriction (every model the endpoint serves). Each entry names its
``modality``, so a chat picker can ask for the ``text`` ones and the global
embedding setting for the ``embedding`` ones.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import Protocol
from coffer.domain.provider.modality import Modality


class ProviderModel(BaseModel):
    """One model on a connection: an opaque id plus what KIND of model it is.

    The same shape is used both ways — the curated entries a connection stores
    and the ids endpoint introspection discovers — so the connection editor can
    round-trip a discovered model into the curated set without reshaping it.
    ``modality`` defaults to ``text``, the kind every curated set held before
    modalities existed.
    """

    id: str = Field(min_length=1, max_length=200)
    modality: Modality = Modality.TEXT


class ProviderCreate(BaseModel):
    """Create an LLM connection. For ``anthropic`` / ``openai`` / ``unknown``
    supply EXACTLY one of ``secret_value`` / ``credential_ref``; an ``ollama``
    connection has no key, so supply neither. ``compatible_agents`` overrides the
    wire default for which agents the connection projects into (``None`` ⇒ default).
    ``models`` curates which of the endpoint's models this connection offers
    downstream, each with its modality (``None`` ⇒ empty ⇒ no restriction)."""

    name: str = Field(min_length=1, max_length=64)
    protocol: Protocol
    base_url: str = Field(min_length=1)
    credential_ref: str | None = None
    secret_value: str | None = Field(default=None, max_length=8192)
    compatible_agents: list[AgentType] | None = None
    models: list[ProviderModel] | None = None
    description: str | None = None


class ProviderPatch(BaseModel):
    """Partial update. ``credential_ref`` is immutable (it is the vault address
    the connection owns); ``protocol`` is not — the probe that guessed the wire
    can be wrong, and nothing keys off it. ``compatible_agents`` is mutable
    (re-target then re-activate to re-project). ``models`` replaces the curated
    set as a whole: ``None`` leaves it alone, ``[]`` clears the restriction."""

    protocol: Protocol | None = None
    base_url: str | None = None
    secret_value: str | None = Field(default=None, max_length=8192)
    compatible_agents: list[AgentType] | None = None
    models: list[ProviderModel] | None = None
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
    curated set of models this connection offers to every downstream picker, each
    carrying its modality; EMPTY means no restriction — the endpoint's whole
    catalogue. A picker takes the entries of the modality it serves, so a chat
    dropdown never offers an embedding or image model. ``internal_default``
    marks the connection Coffer's internal engine uses (at most one globally);
    ``is_active`` marks the one currently projected — a connection may be both.
    """

    name: str
    protocol: Protocol
    base_url: str
    credential_ref: str | None
    compatible_agents: list[AgentType]
    models: list[ProviderModel]
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
    """What an endpoint reports it serves, each id tagged with the modality
    Coffer INFERRED from its name — a pre-fill for the connection editor's
    model table, which the user corrects. Nothing downstream reads this guess:
    once an entry is curated, the stored modality is the truth."""

    models: list[ProviderModel]
    message: str = ""


class EmbeddingTestIn(BaseModel):
    """Probe one embedding model. The endpoint, wire and key come from the named
    CONNECTION — the same connection the global embedding config points at — so
    a test can never be run against settings the config does not hold."""

    connection: str = Field(min_length=1)
    model: str = Field(min_length=1)
