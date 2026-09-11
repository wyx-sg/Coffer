"""``ProviderConfig`` — the ``Resource.config`` payload for kind ``provider``.

Value-level validation only (types, well-formedness). No I/O. A connection is a
credentialed endpoint: ``{protocol, base_url, credential_ref}``. The MODEL it
runs is NOT stored here — it is chosen at the point of use (per-agent binding,
the internal-engine selector, the chat surface), per spec provider-switching amendment E1/E3.
``models`` does not change that: it is the OFFERED set — which of the endpoint's
models the user intends to use — and narrows the menu every point-of-use picker
shows. Empty (the default) means no restriction: everything the endpoint serves.

``protocol`` is the upstream wire the endpoint speaks, detected at create time
(``anthropic`` / ``openai`` / ``ollama`` / ``unknown``); it drives model
introspection and whether a key is needed. It NO LONGER fixes which agent the
connection projects into — that is ``compatible_agents``, an explicit per-
connection set (Claude Code / Codex) the create form pre-fills from the wire but
the user may override (e.g. an openai-compatible gateway routed to Claude Code).
Activation lives in ``is_active`` (≤1 active per agent type, enforced by the
switch op); ``internal_default`` (global, ≤1) marks the connection Coffer's
internal engine uses.

The credential is referenced by ``credential_ref`` only — the raw key lives in
the Fernet vault and is never stored here, mirroring the MCP kind. ``ollama``
connections carry no credential (``credential_ref`` is ``None``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Same ref grammar the credential store accepts (slash-namespaced segments).
_CRED_REF_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+)*$")

# Agent-type identifiers a connection may project into. Held as plain strings
# (mirroring ``AgentType`` values) so this domain module does NOT import the agent
# kind — the cross-kind import contract forbids ``application.memory`` (which
# imports this config for the internal engine) from reaching the agent kind. The
# application layer re-hydrates these into ``AgentType`` at the projection seam.
_CLAUDE_CODE = "claude_code"
_CODEX = "codex"
_KNOWN_AGENTS: frozenset[str] = frozenset({_CLAUDE_CODE, _CODEX})

# Effective agent set when ``compatible_agents`` is unset, by the wire the
# endpoint speaks. ``protocol`` no longer fixes the projection target (the user's
# explicit ``compatible_agents`` does); these are only the defaults the create
# form pre-fills. ollama is internal-only — no key, projects into no agent.
_DEFAULT_COMPATIBLE: dict[str, list[str]] = {
    "anthropic": [_CLAUDE_CODE],
    "openai": [_CODEX],
    "ollama": [],
    "unknown": [_CLAUDE_CODE, _CODEX],
}

#: Shape-only bounds for the curated ``models`` set. Model ids are OPAQUE — they
#: are passed verbatim to the vendor, and Coffer writes down no model name of its
#: own (see the 2026-09-09 amendment: the catalogue is read back from the agents
#: and the endpoints, never authored here). So the only checks are that an id is
#: a non-blank string, that the list holds no duplicates, and that neither the
#: list nor an entry is absurdly long.
_MAX_MODELS = 200
_MAX_MODEL_ID_LEN = 200


class Protocol(StrEnum):
    """Upstream wire protocol a connection speaks (detected, not user-typed).

    ``anthropic`` / ``openai`` fix the agent a connection projects into (Claude
    Code / Codex). ``ollama`` is internal-only: it projects into NO agent and is
    used solely by Coffer's internal LLM engine. ``unknown`` means the probe was
    inconclusive — the connection is offered to every agent and the user decides.
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
    # The agents this connection may project into. ``None`` ⇒ the default for the
    # wire (see ``_DEFAULT_COMPATIBLE``); an explicit list lets the user route any
    # endpoint to any agent (the agnes case: an openai gateway → Claude Code).
    # Empty/None for ollama (internal-only). The projection writer is then chosen
    # by AGENT type, not by ``protocol``. Held as ``AgentType`` value strings (see
    # ``_KNOWN_AGENTS``) to keep this module independent of the agent kind.
    compatible_agents: list[str] | None = None
    # Which of the endpoint's models the user actually intends to use — the
    # OFFERED set, not a chosen model. A picker that offers THIS connection's
    # models (the per-agent binding, the internal-engine selector) narrows to
    # these ids; EMPTY (the default, and what every pre-existing connection has)
    # means no restriction — the endpoint's whole catalogue. An agent's own model
    # catalogue is a separate source and is never narrowed by this. Ids are
    # opaque strings passed verbatim to the vendor; Coffer never checks them
    # against a list of its own.
    models: list[str] = Field(default_factory=list)
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

    @field_validator("compatible_agents")
    @classmethod
    def _known_agents(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        for a in v:
            if a not in _KNOWN_AGENTS:
                raise ValueError(f"unknown compatible agent {a!r}: must be one of {_KNOWN_AGENTS}")
        return v

    @field_validator("models")
    @classmethod
    def _well_formed_models(cls, v: list[str]) -> list[str]:
        """Shape only: non-blank ids, no duplicates, sane bounds. Whether an id
        exists upstream is the endpoint's answer, not ours — a curated set is a
        user's intent, and an id the endpoint stops serving is a stale menu
        entry, not a config error."""
        if len(v) > _MAX_MODELS:
            raise ValueError(f"too many models: at most {_MAX_MODELS}")
        cleaned: dict[str, None] = {}
        for m in v:
            model = m.strip()
            if not model:
                raise ValueError("model id must not be empty")
            if len(model) > _MAX_MODEL_ID_LEN:
                raise ValueError(f"model id too long: at most {_MAX_MODEL_ID_LEN} characters")
            cleaned.setdefault(model, None)
        return list(cleaned)

    @model_validator(mode="after")
    def _credential_matches_protocol(self) -> ProviderConfig:
        """anthropic/openai/unknown connections require a ``credential_ref``; an
        ollama connection (no key) must not carry one, nor any compatible agent
        (it is internal-only and never projects)."""
        if self.protocol is Protocol.OLLAMA:
            if self.credential_ref is not None:
                raise ValueError("ollama connection must not carry a credential_ref")
            if self.compatible_agents:
                raise ValueError("ollama connection projects into no agent")
        elif not self.credential_ref:
            raise ValueError(f"{self.protocol.value} connection requires a credential_ref")
        return self

    def resolved_compatible_agents(self) -> list[str]:
        """The agent-type values this connection projects into: the explicit
        ``compatible_agents`` (deduped, order-preserving) or the wire default.
        Returns ``AgentType`` value strings — the application layer hydrates them
        into ``AgentType`` at the projection seam (keeps this module agent-free)."""
        if self.compatible_agents is None:
            return list(_DEFAULT_COMPATIBLE.get(self.protocol.value, []))
        seen: dict[str, None] = {}
        for a in self.compatible_agents:
            seen.setdefault(a, None)
        return list(seen)


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
