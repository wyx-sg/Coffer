"""``ProviderConfig`` — the ``Resource.config`` payload for kind ``provider``.

Value-level validation only (types, well-formedness). No I/O. A connection is a
credentialed endpoint: ``{protocol, base_url, credential_ref}``. The MODEL it
runs is NOT stored here — it is chosen at the point of use (per-agent binding,
the internal-engine selector, the chat surface), per spec provider-switching amendment E1/E3.
``models`` does not change that: it is the OFFERED set — which of the endpoint's
models the user intends to use — and narrows the menu every point-of-use picker
shows. Empty (the default) means no restriction: everything the endpoint serves.
Each entry carries a ``modality`` (``text`` / ``embedding`` / ``image`` /
``video`` / ``audio``), because one endpoint serves more than chat: a picker
asks for the kind it needs, so a chat dropdown never offers an image model.

``protocol`` is the upstream wire the endpoint speaks, detected at create time
(``anthropic`` / ``openai`` / ``ollama`` / ``unknown``); it drives model
introspection and whether a key is needed. It does NOT fix which agent the
connection projects into: that is the framework-level per-agent **scope** on the
resource row (ADR per-agent-resource-scope), which the user may set to anything (e.g. an
openai-compatible gateway routed to Claude Code). The wire only decides whether
a newly created connection starts DORMANT (``starts_dormant``) — it cannot
supply a starting agent LIST any more, because a scope holds agent uids and no
pure function of this config knows one. Activation lives in
``is_active`` (≤1 active per agent type, enforced by the switch op);
``internal_default`` (global, ≤1) marks the connection Coffer's internal engine
uses.

The credential is referenced by ``credential_ref`` only — the raw key lives in
the Fernet vault and is never stored here, mirroring the MCP kind. ``ollama``
connections carry no credential (``credential_ref`` is ``None``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from coffer.domain.provider.modality import Modality

# Same ref grammar the credential store accepts (slash-namespaced segments).
_CRED_REF_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+)*$")

#: Shape-only bounds for the curated ``models`` set. Model ids are OPAQUE — they
#: are passed verbatim to the vendor, and Coffer writes down no model name of its
#: own (see the 2026-09-09 amendment: the catalogue is read back from the agents
#: and the endpoints, never authored here). So the only checks are that an id is
#: a non-blank string, that the list holds no duplicates, and that neither the
#: list nor an entry is absurdly long.
_MAX_MODELS = 200
_MAX_MODEL_ID_LEN = 200


class CuratedModel(BaseModel):
    """One entry of a connection's offered set: an opaque id plus its kind.

    The modality is what lets one connection serve several surfaces from a
    single credential — a chat picker narrows to ``text`` — instead of every id
    being offered everywhere. It records what the ENDPOINT serves, which is why
    ``embedding`` remains a valid kind although Coffer embeds nothing. It
    is STORED, not derived: Coffer guesses a value only when introspection
    discovers an id the user has not classified yet, and the user corrects it.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    modality: Modality = Modality.TEXT


class Protocol(StrEnum):
    """Upstream wire protocol a connection speaks (detected, not user-typed).

    ``anthropic`` / ``openai`` / ``unknown`` connections start UNSCOPED — open
    to every agent, including one registered tomorrow — and the user narrows
    from there; ``unknown`` means the probe was inconclusive, and the
    conservative answer to that is "ask", not "guess". ``ollama`` is
    internal-only: it starts scoped to NO agent and is used solely by Coffer's
    internal LLM engine.
    """

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"
    UNKNOWN = "unknown"


def starts_dormant(protocol: str) -> bool:
    """Whether a connection on ``protocol`` is CREATED scoped to no agent.

    The whole of what the wire still says about scope, and all it can say. A
    scope names agents by uid (ADR resource-identity-is-an-immutable-uid), and
    a uid is not derivable from this config — so the old table that handed each
    wire a starting agent LIST is gone, along with the ``claude_code`` /
    ``codex`` name strings this module had to spell out to build it. What
    survives is the one case where the framework's default would be wrong
    rather than merely wide: ``ollama`` carries no key, so a scope of "every
    agent" would advertise a reach it can never have. Every other wire starts
    unscoped, which is what "the widest set" now means — and, unlike the
    explicit list it replaces, it keeps covering an agent registered later.

    An unrecognised wire is treated as credentialed, the same answer
    ``unknown`` gets.
    """
    return protocol == Protocol.OLLAMA.value


class ProviderConfig(BaseModel):
    """Resource.config payload when kind == 'provider'."""

    model_config = ConfigDict(extra="forbid")

    protocol: Protocol
    base_url: str
    # Fernet vault ref — an opaque address (``provider/<uuid4>/key``), never
    # derived from anything the user can change; multiple connections MAY
    # share one ref. Required for anthropic/openai/unknown; ``None`` for ollama
    # (no key). Probed for existence at register/update time by the kind's
    # credential_ref_extractor.
    credential_ref: str | None = None
    # Which of the endpoint's models the user actually intends to use — the
    # OFFERED set, not a chosen model. A picker that offers THIS connection's
    # models (the per-agent binding, the internal-engine selector) narrows to
    # these ids AND to the modality it needs; EMPTY (the default, and what every
    # pre-existing connection has) means no restriction — the endpoint's whole
    # catalogue. An agent's own model catalogue is a separate source and is never
    # narrowed by this. Ids are opaque strings passed verbatim to the vendor;
    # Coffer never checks them against a list of its own.
    models: list[CuratedModel] = Field(default_factory=list)
    # At most one active connection per agent type (enforced by the switch op).
    # ollama never projects to an agent, so it stays inactive.
    is_active: bool = False
    # At most one connection globally is Coffer's internal-engine default
    # (enforced by ``ProviderService.set_internal_default``).
    internal_default: bool = False
    # At most one connection globally serves Coffer's speech-to-text
    # (enforced by ``ProviderService.set_transcribe_default``). Separate from
    # ``internal_default`` because they are different models: a gateway that
    # serves chat completions commonly serves no transcription endpoint at
    # all, so borrowing the engine's connection would aim voice at an endpoint
    # that answers 404. There is deliberately NO fallback between the two —
    # nothing marked here means Coffer transcribes nothing and hands the agent
    # the audio file untouched.
    transcribe_default: bool = False

    @field_validator("base_url")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("credential_ref")
    @classmethod
    def _valid_ref(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not _CRED_REF_PATTERN.match(v):
            raise ValueError(
                f"invalid credential_ref {v!r}: must match ^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$"
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
            cleaned.setdefault(model, CuratedModel(id=model, modality=entry.modality))
        return list(cleaned.values())

    @model_validator(mode="after")
    def _credential_matches_protocol(self) -> ProviderConfig:
        """anthropic/openai/unknown connections require a ``credential_ref``; an
        ollama connection (no key) must not carry one. That it projects into no
        agent is no longer a config rule: it is the empty SCOPE such a
        connection is created with, and a keyless connection projects nothing
        whatever its scope says (see ``application.provider.targets``)."""
        if self.protocol is Protocol.OLLAMA:
            if self.credential_ref is not None:
                raise ValueError("ollama connection must not carry a credential_ref")
        elif not self.credential_ref:
            raise ValueError(f"{self.protocol.value} connection requires a credential_ref")
        return self

    def model_ids(self, modality: Modality | None = None) -> list[str]:
        """The curated ids, in the user's order, optionally of ONE modality.

        The narrowing seam: a chat picker asks for ``TEXT`` and can never be
        handed an embedding or image id, while the empty list keeps meaning "no
        restriction" for the caller to interpret.
        """
        return [m.id for m in self.models if modality is None or m.modality is modality]


@dataclass(frozen=True)
class ResolvedConnection:
    """A connection paired with the model to run on it.

    The model lives apart from the connection (spec provider-switching E3), so the two travel
    together when Coffer's internal engine builds a chat model: the connection
    supplies the endpoint + protocol + credential, the ``model`` is resolved
    separately (the internal-engine selector, the per-agent binding, …).
    """

    config: ProviderConfig
    model: str
