"""ModelConfig domain entity and ProviderType enum.

Validation is performed in ``__post_init__`` so that any invalid combination
raises ``ModelRejected`` at construction time, keeping application-layer code
free of cross-cutting validation logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from coffer.domain.errors import ModelRejected


class ProviderType(StrEnum):
    """LLM provider types supported in v1."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OLLAMA = "ollama"

    @classmethod
    def cloud_providers(cls) -> frozenset[ProviderType]:
        """Providers that require a credential reference."""
        return frozenset({cls.ANTHROPIC, cls.OPENAI})


@dataclass(frozen=True)
class ModelConfig:
    """A user-configured LLM that the built-in agent can run on.

    Validation rules (enforced by ``__post_init__``):
    - ``display_name`` must be non-empty (after stripping whitespace).
    - Cloud providers (``anthropic``, ``openai``) require ``credential_ref``.
    - ``ollama`` requires ``base_url``.

    All violations raise ``ModelRejected`` with an appropriate ``reason``.
    """

    id: str
    display_name: str
    provider: ProviderType
    model: str
    credential_ref: str | None
    base_url: str | None
    is_default: bool
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        # Validate display_name first — cheapest check.
        if not self.display_name or not self.display_name.strip():
            raise ModelRejected(
                reason="empty_display_name",
                message="display_name must not be empty",
            )

        # Defensively coerce a raw string (e.g. reconstructed from DB) to the enum.
        object.__setattr__(self, "provider", ProviderType(self.provider))

        provider = self.provider

        if provider in ProviderType.cloud_providers():
            if not self.credential_ref:
                raise ModelRejected(
                    reason="missing_credential",
                    message=(
                        f"provider {provider!r} requires credential_ref; "
                        "store the API key in the OS keychain and pass its reference"
                    ),
                )
        elif provider == ProviderType.OLLAMA and not self.base_url:
            raise ModelRejected(
                reason="missing_base_url",
                message="provider 'ollama' requires base_url (e.g. 'http://localhost:11434')",
            )
