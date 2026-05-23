"""Configuration schema held inside a `memory` Resource's `config` field."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_OLLAMA_ENDPOINT = "http://localhost:11434"
DEFAULT_MAX_MEMORY_CHARS = 8192

LLMProvider = Literal["none", "ollama", "openai"]


class MemoryStoreConfig(BaseModel):
    """Per-store settings. Immutable post-creation except `max_memory_chars`."""

    embedding_model: str = Field(default=DEFAULT_EMBEDDING_MODEL, min_length=1)
    llm_provider: LLMProvider = "none"
    llm_model: str | None = None
    llm_endpoint: str | None = None
    llm_credential_ref: str | None = None
    max_memory_chars: int = Field(default=DEFAULT_MAX_MEMORY_CHARS, ge=64, le=32768)

    def model_post_init(self, __context: object) -> None:
        # Provider-specific requirements.
        if self.llm_provider == "ollama":
            if not self.llm_model:
                raise ValueError("llm_model is required when llm_provider='ollama'")
        elif self.llm_provider == "openai":
            if not self.llm_model:
                raise ValueError("llm_model is required when llm_provider='openai'")
            if not self.llm_credential_ref:
                raise ValueError(
                    "llm_credential_ref is required when llm_provider='openai'; "
                    "store the API key in the OS keychain and pass its reference"
                )

    @property
    def effective_endpoint(self) -> str | None:
        """Resolve the LLM endpoint with provider-default fallback."""
        if self.llm_provider == "ollama":
            return self.llm_endpoint or DEFAULT_OLLAMA_ENDPOINT
        return self.llm_endpoint
