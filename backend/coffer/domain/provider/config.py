"""``ProviderConfig`` — the ``Resource.config`` payload for kind ``provider``.

Value-level validation only (types, well-formedness). No I/O. A connection is
*single-wire*: its ``wire_format`` fixes which agent it projects into
(``anthropic`` → Claude Code, ``openai`` → Codex). ``ollama`` is internal-only —
it projects into NO agent and is used solely by Coffer's internal LLM engine.
Per-wire activation lives in ``is_active`` (the switch op enforces "at most one
active per wire format"); ``internal_default`` (global, ≤1) marks the connection
the internal engine uses — one connection may be both.

The credential is referenced by ``credential_ref`` only — the raw key lives in
the Fernet vault and is never stored here, mirroring the MCP kind. ``ollama``
connections carry no credential (``credential_ref`` is ``None``).
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

# Same ref grammar the credential store accepts (slash-namespaced segments).
_CRED_REF_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+)*$")


class WireFormat(StrEnum):
    """Upstream wire protocol.

    ``anthropic`` / ``openai`` fix the agent a connection projects into (Claude
    Code / Codex). ``ollama`` is internal-only: it projects into NO agent and is
    used solely by Coffer's internal LLM engine.
    """

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"


class WireApi(StrEnum):
    """Codex ``model_providers.*.wire_api`` value (openai profiles only)."""

    CHAT = "chat"
    RESPONSES = "responses"


class ProviderConfig(BaseModel):
    """Resource.config payload when kind == 'provider'."""

    model_config = ConfigDict(extra="forbid")

    wire_format: WireFormat
    base_url: str
    # Fernet vault ref (e.g. ``provider/<name>/key``); multiple connections MAY
    # share one ref. Required for anthropic/openai; ``None`` for ollama (no key).
    # Probed for existence at register/update time by the kind's
    # credential_ref_extractor.
    credential_ref: str | None = None
    # Primary model id → ``ANTHROPIC_MODEL`` (Claude Code) / ``model`` (Codex).
    model: str
    # ``ANTHROPIC_SMALL_FAST_MODEL`` for anthropic; ignored for openai.
    fast_model: str | None = None
    # ``model_providers.*.wire_api`` for openai/Codex; ignored for anthropic.
    wire_api: WireApi = WireApi.CHAT
    # At most one active connection per wire format (enforced by the switch op).
    # ollama never projects to an agent, so it stays inactive.
    is_active: bool = False
    # At most one connection globally is Coffer's internal-engine default
    # (enforced by ``ProviderService.set_internal_default``).
    internal_default: bool = False

    @field_validator("base_url", "model")
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

    @field_validator("fast_model")
    @classmethod
    def _fast_model_non_empty(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not v.strip():
            raise ValueError("fast_model must not be empty if provided")
        return v.strip()

    @model_validator(mode="after")
    def _credential_matches_wire(self) -> ProviderConfig:
        """anthropic/openai connections require a ``credential_ref``; an ollama
        connection (no key) must not carry one."""
        if self.wire_format is WireFormat.OLLAMA:
            if self.credential_ref is not None:
                raise ValueError("ollama connection must not carry a credential_ref")
        elif not self.credential_ref:
            raise ValueError(f"{self.wire_format.value} connection requires a credential_ref")
        return self
