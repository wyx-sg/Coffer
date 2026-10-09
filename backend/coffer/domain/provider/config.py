"""``ProviderConfig`` — the ``Resource.config`` payload for kind ``provider``.

Value-level validation only (types, well-formedness). No I/O. A connection is a
credentialed endpoint: ``{protocol, base_url, secret_ref}``. The MODEL it
runs is NOT stored here — it is chosen at the point of use (per-agent binding,
the chat surface), per spec provider-switching
"Take projected model keys from the agent's binding".
``models`` does not change that: it is the OFFERED set — which of the endpoint's
models the user intends to use — and narrows the menu every point-of-use picker
shows. Empty (the default) means no restriction: everything the endpoint serves.
Each entry carries a ``modality`` (``text`` / ``embedding`` / ``image`` /
``video`` / ``audio``), because one endpoint serves more than chat: a picker
asks for the kind it needs, so a chat dropdown never offers an image model.

``protocol`` is the upstream wire the endpoint speaks, detected at create time
(``anthropic`` / ``openai`` / ``unknown``, plus the retired ``ollama``, which
is no longer offered and only read from a stored file); it drives model
introspection and whether a key is needed. It does NOT fix which agent the
connection projects into: that is the framework-level per-agent **scope** on the
resource row (ADR per-agent-resource-scope), which the user may set to anything (e.g. an
openai-compatible gateway routed to Claude Code). Which connection an agent runs on is
NOT recorded here: it is ``AgentConfig.connection_uid`` on the agent.
``transcribe_default`` (global, ≤1) marks the connection Coffer transcribes
speech with.

The secret is referenced by ``secret_ref`` only — the raw key lives in
the Fernet vault and is never stored here, mirroring the MCP kind. A stored retired ``ollama``
connection carries no secret (``secret_ref`` is ``None``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer,
    model_validator,
)

from coffer.domain.provider.local_runtime import LocalRuntime
from coffer.domain.provider.modality import Modality

# Same ref grammar the secret store accepts (slash-namespaced segments).
_CRED_REF_PATTERN = re.compile(
    r"^\.*[A-Za-z0-9_\-][A-Za-z0-9_.\-]*(/\.*[A-Za-z0-9_\-][A-Za-z0-9_.\-]*)*$"
)

#: Shape-only bounds for the curated ``models`` set. Model ids are OPAQUE — they
#: are passed verbatim to the vendor, and Coffer writes down no model name of its
#: own (see the 2026-09-09 amendment: the catalogue is read back from the agents
#: and the endpoints, never authored here). So the only checks are that an id is
#: a non-blank string, that the list holds no duplicates, and that neither the
#: list nor an entry is absurdly long.
_MAX_MODELS = 200
_MAX_MODEL_ID_LEN = 200


#: Curated-model facts that are omitted from the document while unknown.
_RETIRED_EFFORT_KEYS = ("effort_levels", "default_effort")

#: Connection keys an older build wrote and this one ignores.
_RETIRED_PROVIDER_KEYS = ("internal_default",)

_OPTIONAL_FACTS = ("context_window", "user_context_window", "price")


class CuratedPrice(BaseModel):
    """What the user says this connection charges for a model, in USD per
    million tokens (web search per thousand requests). Relays and resellers
    price differently from the vendor, so a connection's own price wins over
    every other source when usage is costed (spec provider-switching "Resolve
    each model's price from the provider, its API, or the bundled list"). A cache category
    left out is charged at the input rate, so an estimate errs high."""

    model_config = ConfigDict(extra="forbid")

    input: float = Field(ge=0)
    output: float = Field(ge=0)
    cache_write_5m: float | None = Field(default=None, ge=0)
    cache_write_1h: float | None = Field(default=None, ge=0)
    cache_read: float | None = Field(default=None, ge=0)
    web_search: float | None = Field(default=None, ge=0)


class CuratedModel(BaseModel):
    """One entry of a connection's offered set: an opaque id plus its kind.

    The modality is what lets one connection serve several surfaces from a
    single secret — a chat picker narrows to ``text`` — instead of every id
    being offered everywhere. It records what the ENDPOINT serves, which is why
    ``embedding`` remains a valid kind although Coffer embeds nothing. It
    is STORED, not derived: Coffer guesses a value only when introspection
    discovers an id the user has not classified yet, and the user corrects it.
    """

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _drop_retired_effort(cls, data: Any) -> Any:
        """Migration for the removal of reasoning effort: a stored model entry
        may still carry ``effort_levels`` / ``default_effort``; drop them (the
        file loses the keys on its next write)."""
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k not in _RETIRED_EFFORT_KEYS}
        return data

    id: str
    modality: Modality = Modality.TEXT
    #: The context window the endpoint reports serving this model with, in
    #: tokens (a local runtime's served window, a listing's
    #: ``max_input_tokens`` / ``context_length``). ``None``: it reported none.
    context_window: int | None = Field(default=None, ge=1024, le=100_000_000)
    #: The window the person set for this model on this connection; it wins
    #: over the endpoint's and the bundled list's (spec provider-switching
    #: "Resolve each provider model's context window"). ``None``: not set.
    user_context_window: int | None = Field(default=None, ge=1024, le=100_000_000)
    #: This connection's own price for the model; ``None``: resolved elsewhere.
    price: CuratedPrice | None = None

    @model_serializer(mode="wrap")
    def _omit_unknowns(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """An unrecorded fact is left out of the stored (and synced) document
        rather than written as ``null``, so an entry that records nothing new
        reads exactly as it did before these fields existed."""
        data: dict[str, Any] = handler(self)
        for key in _OPTIONAL_FACTS:
            if data.get(key) is None:
                data.pop(key, None)
        return data


class Protocol(StrEnum):
    """Upstream wire protocol a connection speaks (detected, not user-typed).

    ``anthropic`` / ``openai`` / ``unknown`` connections start UNSCOPED — open
    to every agent, including one registered tomorrow — and the user narrows
    from there; ``unknown`` means the probe was inconclusive, and the
    conservative answer to that is "ask", not "guess". ``ollama`` is a
    retired value: it is no longer offered, and a stored one is only read
    (and deleted) — it starts scoped to NO agent and reaches none.
    """

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"
    UNKNOWN = "unknown"


def is_loopback_url(url: str) -> bool:
    """Whether ``url`` names this machine (``localhost`` or a loopback IP)."""
    import ipaddress
    from urllib.parse import urlparse

    host = (urlparse(url if "://" in url else f"http://{url}").hostname or "").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class ProviderConfig(BaseModel):
    """Resource.config payload when kind == 'provider'."""

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _drop_retired_keys(cls, data: Any) -> Any:
        """A stored connection may still carry ``internal_default``, which no
        longer marks anything; drop it, and the file loses the key on its next
        write (spec provider-switching "Ignore a stored internal-default flag")."""
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k not in _RETIRED_PROVIDER_KEYS}
        return data

    protocol: Protocol
    base_url: str
    # Where an OpenAI-protocol endpoint ALSO serves the Anthropic Messages wire,
    # when that is not at ``base_url`` (DeepSeek: ``https://api.deepseek.com``
    # and ``…/anthropic``). Claude Code is reached there, Codex at ``base_url``,
    # so one connection serves both (ADR one-connection-serves-both-wires).
    # ``None``: no second address.
    anthropic_base_url: str | None = None
    # Fernet vault ref — an opaque address (``provider/<uuid4>/key``), never
    # derived from anything the user can change; multiple connections MAY
    # share one ref. Required for anthropic/openai/unknown; ``None`` for ollama
    # (no key). Probed for existence at register/update time by the kind's
    # secret_ref_extractor.
    secret_ref: str | None = None
    # Which of the endpoint's models the user actually intends to use — the
    # OFFERED set, not a chosen model. A picker that offers THIS connection's
    # models (the per-agent binding) narrows to
    # these ids AND to the modality it needs; EMPTY (the default, and what every
    # pre-existing connection has) means no restriction — the endpoint's whole
    # catalogue. An agent's own model catalogue is a separate source and is never
    # narrowed by this. Ids are opaque strings passed verbatim to the vendor;
    # Coffer never checks them against a list of its own.
    models: list[CuratedModel] = Field(default_factory=list)
    # At most one connection globally serves Coffer's speech-to-text
    # (enforced by ``ProviderService.set_transcribe_default``). A gateway that
    # serves chat completions commonly serves no transcription endpoint at
    # all, so nothing marked here means Coffer transcribes nothing and hands
    # the agent the audio file untouched.
    transcribe_default: bool = False
    # Set when the endpoint is a model runtime on this machine (Ollama, LM
    # Studio, vLLM, llama-server): what detection found there. Such a
    # connection carries no key and is reached through the model proxy like
    # any other (spec provider-switching "Configure a local model connection").
    local_runtime: LocalRuntime | None = None

    @model_serializer(mode="wrap")
    def _omit_absent_runtime(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """A connection that is no local runtime carries no ``local_runtime``
        key at all, so every existing document keeps its shape."""
        data: dict[str, Any] = handler(self)
        for key in ("local_runtime", "anthropic_base_url"):
            if data.get(key) is None:
                data.pop(key, None)
        return data

    @field_validator("base_url")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("anthropic_base_url")
    @classmethod
    def _blank_is_none(cls, v: str | None) -> str | None:
        return v.strip() or None if v is not None else None

    @field_validator("secret_ref")
    @classmethod
    def _valid_ref(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _CRED_REF_PATTERN.match(v):
            raise ValueError(
                f"invalid secret_ref {v!r}: slash-separated [A-Za-z0-9_.-] segments, none only dots"
            )
        return v

    @field_validator("models")
    @classmethod
    def _well_formed_models(cls, v: list[CuratedModel]) -> list[CuratedModel]:
        """Shape only: non-blank ids, no duplicate ids, sane bounds. Whether an
        id exists upstream is the endpoint's answer, not ours — a curated set is
        a user's intent, and an id the endpoint stops serving is a stale menu
        entry, not a config error. Nor is the MODALITY checked against the
        vendor: the user's answer wins over anything Coffer could guess."""
        if len(v) > _MAX_MODELS:
            raise ValueError(f"too many models: at most {_MAX_MODELS}")
        cleaned: dict[str, CuratedModel] = {}
        for entry in v:
            model = entry.id.strip()
            if not model:
                raise ValueError("model id must not be empty")
            if len(model) > _MAX_MODEL_ID_LEN:
                raise ValueError(f"model id too long: at most {_MAX_MODEL_ID_LEN} characters")
            cleaned.setdefault(model, entry.model_copy(update={"id": model}))
        return list(cleaned.values())

    @model_validator(mode="after")
    def _secret_matches_protocol(self) -> ProviderConfig:
        """anthropic/openai/unknown connections require a ``secret_ref``
        unless they are a local runtime, whose key is optional (LM Studio,
        vLLM and llama-server can be started with one); a stored, retired
        ollama-protocol connection has no key and stays readable."""
        if self.protocol is Protocol.OLLAMA:
            pass
        elif not self.secret_ref and self.local_runtime is None:
            raise ValueError(f"{self.protocol.value} connection requires a secret_ref")
        if self.local_runtime is not None and not is_loopback_url(self.base_url):
            raise ValueError("a local runtime connection must point at this machine (loopback)")
        if self.anthropic_base_url is not None and (
            self.protocol is not Protocol.OPENAI or self.local_runtime is not None
        ):
            raise ValueError("only a remote openai connection takes a second, Anthropic address")
        return self

    def served_wires(self) -> frozenset[str]:
        """The wires this connection has an address for — what decides which
        agents it can serve (ADR one-connection-serves-both-wires): an
        Anthropic connection serves the Anthropic wire; an OpenAI one the OpenAI
        wire, and the Anthropic wire too when it names an Anthropic address; a
        local runtime what detection found it serving; an ``unknown`` one both,
        since the probe could not tell and the switch test decides; a retired
        ``ollama`` one none."""
        if self.protocol is Protocol.OLLAMA:
            return frozenset()
        if self.local_runtime is not None and self.local_runtime.wires:
            return frozenset(self.local_runtime.wires) | {self.protocol.value}
        if self.protocol is Protocol.UNKNOWN:
            return frozenset({Protocol.ANTHROPIC.value, Protocol.OPENAI.value})
        if self.protocol is Protocol.OPENAI and self.anthropic_base_url:
            return frozenset({Protocol.ANTHROPIC.value, Protocol.OPENAI.value})
        return frozenset({self.protocol.value})

    def base_url_for(self, anthropic: bool) -> str:
        """Where this connection serves a wire: the Anthropic address for the
        Anthropic wire when it has one, else ``base_url``."""
        if anthropic and self.anthropic_base_url:
            return self.anthropic_base_url
        return self.base_url

    @property
    def is_local(self) -> bool:
        """A model runtime on this machine."""
        return self.local_runtime is not None

    def model_ids(self, modality: Modality | None = None) -> list[str]:
        """The curated ids, in the user's order, optionally of ONE modality.

        The narrowing seam: a chat picker asks for ``TEXT`` and can never be
        handed an embedding or image id. An empty answer is ambiguous on its
        own — nothing curated at all ("no restriction") or nothing of THIS
        modality — so a caller that must tell them apart checks ``models``
        itself (spec provider-switching "Offer only text models to chat
        pickers").
        """
        return [m.id for m in self.models if modality is None or m.modality is modality]

    def curated(self, model_id: str | None) -> CuratedModel | None:
        """The curated entry for ``model_id``, or ``None``."""
        if model_id is None:
            return None
        return next((m for m in self.models if m.id == model_id), None)


@dataclass(frozen=True)
class ResolvedConnection:
    """A connection paired with the model to run on it.

    The model lives apart from the connection (spec provider-switching
    "Take projected model keys from the agent's binding"), so the two travel
    together when Coffer calls the connection: the connection supplies the
    endpoint + protocol + secret, the ``model`` is resolved separately (the
    speech-to-text selector, the per-agent binding, …).
    """

    config: ProviderConfig
    model: str
