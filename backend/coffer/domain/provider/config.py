"""``ProviderConfig`` — the ``Resource.config`` payload for kind ``provider``.

Value-level validation only (types, well-formedness). No I/O. A connection is a
credentialed endpoint: ``{protocol, base_url, credential_ref}``. The MODEL it
runs is NOT stored here — it is chosen at the point of use (per-agent binding,
the internal-engine selector, the chat surface), per spec 011 amendment E1/E3.

``protocol`` is the upstream wire it speaks, detected at create/edit time:
``anthropic`` → Claude Code, ``openai`` → Codex, ``ollama`` (internal-only,
projects into no agent), or ``unknown`` when the probe was inconclusive (the
connection is then offered to every agent and the user decides). Per-wire
activation lives in ``is_active``; ``internal_default`` (global, ≤1) marks the
connection Coffer's internal engine uses.

The credential is referenced by ``credential_ref`` only — the raw key lives in
the Fernet vault and is never stored here, mirroring the MCP kind. ``ollama``
connections carry no credential (``credential_ref`` is ``None``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# Same ref grammar the credential store accepts (slash-namespaced segments).
_CRED_REF_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+)*$")


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
    # At most one active connection per protocol (enforced by the switch op).
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

    @model_validator(mode="after")
    def _credential_matches_protocol(self) -> ProviderConfig:
        """anthropic/openai/unknown connections require a ``credential_ref``; an
        ollama connection (no key) must not carry one."""
        if self.protocol is Protocol.OLLAMA:
            if self.credential_ref is not None:
                raise ValueError("ollama connection must not carry a credential_ref")
        elif not self.credential_ref:
            raise ValueError(f"{self.protocol.value} connection requires a credential_ref")
        return self


@dataclass(frozen=True)
class ResolvedConnection:
    """A connection paired with the model to run on it.

    The model lives apart from the connection (spec 011 E3), so the two travel
    together when Coffer's internal engine builds a chat model: the connection
    supplies the endpoint + protocol + credential, the ``model`` is resolved
    separately (the internal-engine selector, the per-agent binding, …).
    """

    config: ProviderConfig
    model: str
