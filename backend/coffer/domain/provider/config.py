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
openai-compatible gateway routed to Claude Code). The wire only supplies the
STARTING scope a newly created connection is given
(``default_scope_for_protocol``), so a fresh connection behaves as it always
did and the user narrows or widens it from there. Activation lives in
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

# Agent-type identifiers a connection may project into. Held as plain strings
# (mirroring ``AgentType`` values) so this domain module does NOT import the agent
# kind — the cross-kind import contract forbids ``application.memory`` (which
# imports this config for the internal engine) from reaching the agent kind. The
# application layer re-hydrates these into ``AgentType`` at the projection seam.
_CLAUDE_CODE = "claude_code"
_CODEX = "codex"

# The scope a connection is CREATED with, by the wire the endpoint speaks. The
# wire does not fix the projection target — the resource's scope does, and the
# user may edit it — so a credentialed endpoint starts at the widest set (both
# agents) and is narrowed from there. ollama is internal-only: no key, projects
# into no agent, so it starts dormant.
#
# This is only a starting value. Were it absent, the framework's own default
# for an unset scope ("every agent") would silently widen a new ollama
# connection into both agents, which is why the provider kind supplies it
# through ``Kind.default_scope`` instead of letting the framework default win.
_DEFAULT_SCOPE: dict[str, list[str]] = {
    "anthropic": [_CLAUDE_CODE, _CODEX],
    "openai": [_CLAUDE_CODE, _CODEX],
    "ollama": [],
    "unknown": [_CLAUDE_CODE, _CODEX],
}


def default_scope_for_protocol(protocol: str) -> list[str]:
    """The per-agent scope a connection on ``protocol`` is created with.

    Agent-type VALUE strings, like every other agent reference in this module —
    the application layer hydrates them at the projection seam so this module
    stays independent of the agent kind. An unrecognised wire gets the widest
    set, the same answer ``unknown`` gets.
    """
    return list(_DEFAULT_SCOPE.get(protocol, [_CLAUDE_CODE, _CODEX]))


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

    ``anthropic`` / ``openai`` set the scope a connection STARTS with (both
    coding agents). ``ollama`` is internal-only: it starts scoped to NO agent
    and is used solely by Coffer's internal LLM engine. ``unknown`` means the
    probe was inconclusive — the connection starts open to every agent and the
    user decides.
    """

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"
    UNKNOWN = "unknown"


class ProviderConfig(BaseModel):
    """Resource.config payload when kind == 'provider'."""

    model_config = ConfigDict(extra="forbid")

    protocol: Protocol
    base_url: str
    # Fernet vault ref (e.g. ``provider/<name>/key``); multiple connections MAY
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
