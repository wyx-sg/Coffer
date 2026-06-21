"""``ProviderConfig`` — the ``Resource.config`` payload for kind ``provider``.

Value-level validation only (types, well-formedness). No I/O. A profile is
*single-wire*: its ``wire_format`` fixes which agent it can project into
(``anthropic`` → Claude Code, ``openai`` → Codex). Per-wire activation lives in
``is_active`` (the switch op enforces "at most one active per wire format").

The credential is referenced by ``credential_ref`` only — the raw key lives in
the Fernet vault and is never stored here, mirroring the MCP / model kinds.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

# Same ref grammar the credential store accepts (slash-namespaced segments).
_CRED_REF_PATTERN = re.compile(r"^[A-Za-z0-9_.\-]+(/[A-Za-z0-9_.\-]+)*$")


class WireFormat(StrEnum):
    """Upstream wire protocol — fixes the agent a profile projects into."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class WireApi(StrEnum):
    """Codex ``model_providers.*.wire_api`` value (openai profiles only)."""

    CHAT = "chat"
    RESPONSES = "responses"


class ProviderConfig(BaseModel):
    """Resource.config payload when kind == 'provider'."""

    model_config = ConfigDict(extra="forbid")

    wire_format: WireFormat
    base_url: str
    # Fernet vault ref (e.g. ``provider/<name>/key``); multiple profiles MAY
    # share one ref. Probed for existence at register/update time by the kind's
    # credential_ref_extractor.
    credential_ref: str
    # Primary model id → ``ANTHROPIC_MODEL`` (Claude Code) / ``model`` (Codex).
    model: str
    # ``ANTHROPIC_SMALL_FAST_MODEL`` for anthropic; ignored for openai.
    fast_model: str | None = None
    # ``model_providers.*.wire_api`` for openai/Codex; ignored for anthropic.
    wire_api: WireApi = WireApi.CHAT
    # At most one active profile per wire format (enforced by the switch op).
    is_active: bool = False

    @field_validator("base_url", "model")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

    @field_validator("credential_ref")
    @classmethod
    def _valid_ref(cls, v: str) -> str:
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
