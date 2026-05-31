"""`BuiltinAgentConfig` — Pydantic schema stored on `Resource.config` for
kind == ``builtin_agent``.

Pure, value-level validation only (no I/O). The provider/model string is
opaque here — it is resolved by the LangGraph runtime in infrastructure
(``init_chat_model``), so the domain stays free of any engine dependency.
"""

from __future__ import annotations

from fnmatch import fnmatch

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BuiltinAgentConfig(BaseModel):
    """Resource.config payload when kind == 'builtin_agent'."""

    model_config = ConfigDict(extra="forbid")

    # Provider-qualified model id, e.g. ``anthropic:claude-sonnet-4-6``,
    # ``openai:gpt-4o``, ``ollama:llama3``. Resolved by the engine adapter.
    model: str = Field(min_length=1)
    system_prompt: str | None = None
    # Sampling knobs (optional — the engine applies provider defaults if unset).
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)
    # Keychain ref for the provider API key (cloud providers). ``None`` for
    # local providers (Ollama) or when the key is supplied via the environment.
    credential_ref: str | None = None
    # When true the agent is given Coffer's own MCP gateway tools (every MCP
    # server / skill / knowledge base / memory the vault manages).
    use_gateway: bool = True
    # Tool-name glob patterns that require human confirmation before running.
    # Empty = no confirmation gating. The seeded default agent ships with a
    # conservative destructive-op set (see the seeding helper).
    confirm_tools: list[str] = Field(default_factory=list)

    @field_validator("model")
    @classmethod
    def _model_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("model must not be blank")
        return v

    def requires_confirmation(self, tool_name: str) -> bool:
        """True if ``tool_name`` matches any ``confirm_tools`` glob pattern."""
        return any(fnmatch(tool_name, pattern) for pattern in self.confirm_tools)
