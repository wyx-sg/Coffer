"""Request / response schemas for ``/api/v1/providers`` (spec provider-switching).

``ProviderOut`` NEVER carries the secret — only its ``credential_ref``. A
connection is a credentialed endpoint ``{protocol, base_url, credential_ref}``;
the model lives apart from it (spec provider-switching "Take projected model
keys from the agent's binding") and is chosen at the point of use.
``models`` is the curated set the connection OFFERS to that choice — empty means
no restriction (every model the endpoint serves). Each entry names its
``modality`` — what the ENDPOINT serves, since one base URL answers for chat,
embeddings, images and more — so a chat picker can ask for the ``text`` ones.
Coffer itself embeds nothing.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import CuratedPrice, Protocol
from coffer.domain.provider.local_runtime import LocalRuntime
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
    #: The context window the endpoint serves the model with, in tokens;
    #: ``None`` when unknown (never guessed).
    context_window: int | None = Field(default=None, ge=1024, le=100_000_000)
    #: The reasoning-effort levels the model accepts; ``None`` when it takes none.
    effort_levels: list[str] | None = None
    #: The level used when an agent's binding names none.
    default_effort: str | None = None
    #: This connection's own price for the model (USD per million tokens);
    #: ``None``: the bundled price list, or unpriced.
    price: CuratedPrice | None = None


class ProviderCreate(BaseModel):
    """Create an LLM connection. For ``anthropic`` / ``openai`` / ``unknown``
    supply EXACTLY one of ``secret_value`` / ``credential_ref``; an ``ollama``
    connection has no key, so supply neither. WHICH agents the connection
    projects into is not set here: the new connection starts on the wire's own
    default scope and is re-targeted through the framework's scope surface
    (``PUT /api/v1/resources/{uid}/scope``), the same one every scoped
    kind uses. ``models`` curates which of the endpoint's models this connection
    offers downstream, each with its modality (``None`` ⇒ empty ⇒ no restriction)."""

    name: str = Field(min_length=1, max_length=64)
    protocol: Protocol
    base_url: str = Field(min_length=1)
    credential_ref: str | None = None
    secret_value: str | None = Field(default=None, max_length=8192)
    models: list[ProviderModel] | None = None
    description: str | None = None
    #: What ``POST /providers/detect-local`` found at a loopback endpoint; set,
    #: the connection is a local runtime and may carry no key.
    local_runtime: LocalRuntime | None = None


class ProviderPatch(BaseModel):
    """Partial update. ``credential_ref`` is immutable (it is the vault address
    the connection owns); ``protocol`` is not — the probe that guessed the wire
    can be wrong, so it is corrected in place rather than by re-entering the
    connection, key and all.

    The wire DOES decide one thing, though, so that correction is refused with
    409 ``PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE`` while the connection is
    ``is_active``: an ``ollama`` connection covers no agent whatever its scope
    says. Moving the wire under a live projection would leave the native config
    already written with nothing that would ever take it off. Revert the agents to their
    built-in login, patch, then re-activate. An inactive connection patches
    freely.

    Re-targeting which agents the connection projects into is a scope edit, not
    a patch field (re-target then re-activate to re-project). ``models``
    replaces the curated set as a whole: ``None`` leaves it alone, ``[]`` clears
    the restriction."""

    protocol: Protocol | None = None
    base_url: str | None = None
    secret_value: str | None = Field(default=None, max_length=8192)
    models: list[ProviderModel] | None = None
    description: str | None = None


class ProviderOut(BaseModel):
    """An LLM connection as returned by the API (no secret).

    ``credential_ref`` is ``None`` for ``ollama`` connections (no key).
    ``compatible_agents`` is the CONFIGURED reach — the agent types this
    connection's per-agent scope (ADR per-agent-resource-scope) covers among the
    agents Coffer knows, not narrowed by ``enabled``, and empty for a keyless
    (ollama) connection — so the UI can filter agents without re-deriving it.
    It is READ-ONLY: it is reported here, and changed through the scope
    surface. ``models`` is the
    curated set of models this connection offers to every downstream picker, each
    carrying its modality; EMPTY means no restriction — the endpoint's whole
    catalogue. A picker takes the entries of the modality it serves, so a chat
    dropdown never offers an embedding or image model. ``internal_default``
    marks the connection Coffer's internal engine uses (at most one globally),
    ``transcribe_default`` the one it transcribes speech on — a separate flag
    because they are separate models and neither falls back to the other; and
    ``is_active`` marks the one currently projected. A connection may carry any
    combination.

    ``uid`` is the connection's identity and what every route here takes; the
    ``name`` beside it is the label, free to change through
    ``PATCH /api/v1/resources/{uid}`` without anything downstream noticing. That
    is the whole reason this kind no longer owns a rename operation of its own:
    nothing Coffer projects into an agent's config names the connection (the
    ``apiKeyHelper`` prints the agent's local proxy token), so a rename rewrites
    nothing (ADR resource-identity-is-an-immutable-uid).
    """

    uid: str
    name: str
    #: The display title a person chose (spec resource-framework "Carry an optional
    #: editable title on the kinds that have one"); ``None`` when unset, and a surface shows
    #: the name in its place.
    title: str | None = None
    protocol: Protocol
    base_url: str
    credential_ref: str | None
    compatible_agents: list[AgentType]
    models: list[ProviderModel]
    is_active: bool
    internal_default: bool
    transcribe_default: bool
    enabled: bool
    description: str | None
    created_at: datetime
    #: The local runtime this connection points at, or ``None`` for a remote one.
    local_runtime: LocalRuntime | None = None
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
    """Result of switching an agent type back to its own built-in login."""

    agent_type: AgentType
    deprojected: list[str]
    previous: str | None = None


# ---------------------------------------------------------------------------
# Introspection: probe a connection, list what it serves.
#
# These moved here from the chat page's schema module when that page was
# removed. They were never chat schemas — the connection editor is what posts
# to /api/v1/models.
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
    #: False only when the listing call failed; an empty answer is reachable,
    #: so a caller need not read ``message`` to tell the two apart.
    reachable: bool = True


class DetectLocalIn(BaseModel):
    """Probe one loopback URL, or — with none — each runtime's default port."""

    base_url: str | None = None


class LocalModelOut(BaseModel):
    id: str
    #: The window the runtime serves the model with; ``None`` when it does not say.
    context_window: int | None = None
    #: Whether the runtime says the model can call tools; ``None`` when unknown.
    tools: bool | None = None


class LocalRuntimeOut(BaseModel):
    base_url: str
    runtime: LocalRuntime
    models: list[LocalModelOut]


class DetectLocalOut(BaseModel):
    found: list[LocalRuntimeOut]
