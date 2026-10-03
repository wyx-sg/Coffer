"""Request / response schemas for ``/api/v1/providers`` (spec provider-switching).

``ProviderOut`` NEVER carries the secret — only its ``secret_ref``. A
connection is a credentialed endpoint ``{protocol, base_url, secret_ref}``;
the model lives apart from it (spec provider-switching "Take projected model
keys from the agent's binding") and is chosen at the point of use.
``models`` is the curated set the connection OFFERS to that choice — empty means
no restriction (every model the endpoint serves). Each entry names its
``modality`` — what the ENDPOINT serves, since one base URL answers for chat,
embeddings, images and more — so a chat picker can ask for the ``text`` ones.
Coffer itself embeds nothing.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from coffer.domain.agent.types import AgentType
from coffer.domain.provider.config import CuratedPrice, Protocol
from coffer.domain.provider.local_runtime import LocalRuntime
from coffer.domain.provider.modality import Modality
from coffer.domain.usage.pricing import PriceSource
from coffer.surfaces.http.handoff_schemas import HandoffOut


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
    #: ``None``: the provider API's, the bundled list's, or none.
    price: CuratedPrice | None = None


class ProviderCreate(BaseModel):
    """Create an LLM connection. For ``anthropic`` / ``openai`` / ``unknown``
    supply EXACTLY one of ``secret_value`` / ``secret_ref``; an ``ollama``
    connection has no key, so supply neither. WHICH agents the connection
    projects into is not set here: the new connection starts on the wire's own
    default scope and is re-targeted through the framework's scope surface
    (``PUT /api/v1/resources/{uid}/scope``), the same one every scoped
    kind uses. ``models`` curates which of the endpoint's models this connection
    offers downstream, each with its modality (``None`` ⇒ empty ⇒ no restriction)."""

    name: str = Field(min_length=1, max_length=64)
    protocol: Protocol
    base_url: str = Field(min_length=1)
    secret_ref: str | None = None
    secret_value: str | None = Field(default=None, max_length=8192)
    models: list[ProviderModel] | None = None
    description: str | None = None
    #: What ``POST /providers/detect-local`` found at a loopback endpoint; set,
    #: the connection is a local runtime and may carry no key.
    local_runtime: LocalRuntime | None = None


class ProviderPatch(BaseModel):
    """Partial update. ``secret_ref`` is immutable (it is the vault address
    the connection owns); ``protocol`` is not — the probe that guessed the wire
    can be wrong, so it is corrected in place rather than by re-entering the
    connection, key and all.

    The wire DOES decide one thing, though: an ``ollama`` connection covers no
    agent whatever its scope says. So the correction is refused with 409
    ``PROVIDER_PROTOCOL_LOCKED_WHILE_ACTIVE`` while an agent runs on the
    connection — moving the wire under a live projection would leave the native
    config already written with nothing that would ever take it off. Revert those
    agents to their built-in login, patch, then switch them back. A connection no
    agent runs on patches freely.

    Re-targeting which agents the connection projects into is a scope edit, not
    a patch field (re-target then re-activate to re-project). ``models``
    replaces the curated set as a whole: ``None`` leaves it alone, ``[]`` clears
    the restriction."""

    protocol: Protocol | None = None
    base_url: str | None = None
    secret_value: str | None = Field(default=None, max_length=8192)
    models: list[ProviderModel] | None = None
    description: str | None = None
    #: "Use as fallback for other providers": whether another provider's
    #: request may fail over here. ``None`` leaves it alone.
    fallback: bool | None = None


class ProviderOut(BaseModel):
    """An LLM connection as returned by the API (no secret).

    ``secret_ref`` is ``None`` for ``ollama`` connections (no key).
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
    because they are separate models and neither falls back to the other. A
    connection may carry either, both or neither. Which agents run on it is not a
    field here: it is each agent's ``connection_uid``.

    ``uid`` is the connection's identity and what every route here takes; the
    ``name`` beside it is the label, free to change through
    ``PATCH /api/v1/resources/{uid}`` without anything downstream noticing. That
    is the whole reason this kind no longer owns a rename operation of its own:
    nothing Coffer projects into an agent's config names the connection (the
    ``apiKeyHelper`` prints the agent's local proxy token), so a rename rewrites
    nothing (ADR identity-is-the-uid-inside-the-file).
    """

    uid: str
    name: str
    #: The display title a person chose (spec resource-framework "Carry an optional
    #: editable title on the kinds that have one"); ``None`` when unset, and a surface shows
    #: the name in its place.
    title: str | None = None
    protocol: Protocol
    base_url: str
    secret_ref: str | None
    compatible_agents: list[AgentType]
    models: list[ProviderModel]
    internal_default: bool
    transcribe_default: bool
    enabled: bool
    description: str | None
    created_at: datetime
    #: The local runtime this connection points at, or ``None`` for a remote one.
    local_runtime: LocalRuntime | None = None
    #: "Use as fallback for other providers" (default on). A local runtime is
    #: never a fallback whatever this says.
    fallback: bool = True
    updated_at: datetime


class ProviderListOut(BaseModel):
    """Every connection in Model providers list order — which is also the
    order the model proxy tries fallbacks in."""

    providers: list[ProviderOut]


class ProviderOrderIn(BaseModel):
    """The new list order: every connection's uid, exactly once."""

    uids: list[str] = Field(min_length=1, max_length=500)


class ModelPricesIn(BaseModel):
    """The models whose price on this provider to resolve."""

    models: list[str] = Field(max_length=1000)


class ModelPriceOut(BaseModel):
    """One model's price on a provider and where it came from (spec
    provider-switching "Resolve each model's price from the provider, its API,
    or the bundled list"). USD per million tokens; ``source`` ``None`` means no
    price is known and every rate is ``None`` — shown as "—", never as zero.
    ``source_name`` names the provider whose API reported it (``provider``) or
    the price list's provider (``bundled``). ``tiered``: the rates shown are
    the base tier; past a threshold of input tokens the request pays more."""

    model: str
    source: PriceSource | None = None
    source_name: str | None = None
    input: float | None = None
    output: float | None = None
    cache_write_5m: float | None = None
    cache_write_1h: float | None = None
    cache_read: float | None = None
    tiered: bool = False
    #: For ``bundled``: the day the price list in use was taken from
    #: genai-prices — "Bundled · updated <date>".
    source_updated: date | None = None


class ModelPricesOut(BaseModel):
    prices: list[ModelPriceOut]
    #: The price list in use (``genai-prices@<commit or refresh day>…``).
    bundled_version: str


class PriceListOut(BaseModel):
    """The price list pricing reads now, and its daily refresh (spec
    provider-switching "Refresh the bundled price list in the background")."""

    version: str
    #: The day its data was taken from genai-prices; ``None`` when unknown.
    updated: date | None
    #: ``refreshed``: fetched by the daily refresh; ``bundled``: shipped in this build.
    origin: Literal["bundled", "refreshed"]
    #: The machine's setting (Settings > General).
    refresh: bool
    #: ``COFFER_PRICE_REFRESH=off`` pins the refresh off whatever the setting says.
    pinned_off: bool
    last_attempt_at: datetime | None = None
    last_error: str | None = None


class PriceListIn(BaseModel):
    refresh: bool


class ActivateIn(BaseModel):
    """Which agent to switch onto the connection. There is one agent per type
    (spec agent-registry "Keep one agent per type, named by it"), so the type
    names it; the switch changes that agent and no other."""

    agent_type: AgentType


class ActivateOut(BaseModel):
    """Result of switching one agent onto a connection."""

    activated: str
    protocol: Protocol
    agent_type: AgentType
    #: The agent's name.
    agent: str


class DeactivateOut(BaseModel):
    """Result of switching an agent type back to its own built-in login."""

    agent_type: AgentType
    deprojected: list[str]
    previous: str | None = None


class DeletePreviewLine(BaseModel):
    kind: Literal["context", "add", "remove", "hunk"]
    text: str
    old_no: int | None = None
    new_no: int | None = None


class DeletePreviewFileOut(BaseModel):
    """One agent file that deleting the connection would change."""

    #: Absolute path.
    path: str
    op: Literal["modify", "remove"]
    diff: list[DeletePreviewLine]


class DeletePreviewAgentOut(BaseModel):
    agent_uid: str
    agent_type: AgentType
    agent_name: str
    files: list[DeletePreviewFileOut]


class ProviderDeletePreviewOut(BaseModel):
    """What deleting a connection does to the agents running on it."""

    agents: list[DeletePreviewAgentOut]


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
    secret_ref: str | None = None
    secret_value: str | None = None  # inline secret to test before saving
    base_url: str | None = None


class ListModelsIn(BaseModel):
    provider: str
    secret_ref: str | None = None
    secret_value: str | None = None  # inline secret to fetch before saving
    base_url: str | None = None


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
    #: With nothing found, the prompt that hands setting a runtime up to the
    #: person's agent (``application/provider/local_runtime_handoff.py``);
    #: ``None`` once one answers.
    handoff: HandoffOut | None = None


# ---------------------------------------------------------------------------
# Change model: review what a model switch writes, then write it.
# ---------------------------------------------------------------------------


class ModelSwitchIn(BaseModel):
    """What the agent page's Change model dialog asks for.

    ``connection_uid`` ``null`` is the agent's own built-in login: no model,
    effort or tiers are written, and Coffer removes only the keys it wrote.
    ``seen`` is sent only to apply: each previewed file's path with the
    fingerprint the preview read, so a file edited since is refused."""

    agent_type: AgentType
    connection_uid: str | None = None
    model: str | None = None
    effort: str | None = None
    tier_models: dict[str, str] | None = None
    #: A local model's context window in tokens, when its runtime reports none.
    context_window: int | None = None
    seen: dict[str, str] | None = None


class ModelSwitchLine(BaseModel):
    kind: Literal["context", "add", "remove", "hunk"]
    text: str
    old_no: int | None = None
    new_no: int | None = None


class ModelSwitchFile(BaseModel):
    """One file the switch changes (or would change)."""

    path: str
    op: Literal["add", "modify", "remove"]
    added: int
    removed: int
    diff: list[ModelSwitchLine]
    #: What the file held when this was computed; sent back as ``seen``.
    fingerprint: str


class ModelSwitchOut(BaseModel):
    agent_uid: str
    agent_name: str
    #: The connection the agent runs on after the switch; ``null``: its built-in login.
    connection_name: str | None = None
    files: list[ModelSwitchFile]
