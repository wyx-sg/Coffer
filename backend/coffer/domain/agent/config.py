"""`AgentConfig` — Pydantic schema stored on `Resource.config` for kind=agent.

Validation here is *value-level only* (types, ranges, well-formedness). Path
writability is asserted at registration time in `application/agent/service`
because it is an I/O check and domain stays pure.

An agent has a single user-facing directory: its **config dir** (`~/.claude`,
`~/.codex`, …). It defaults to the type's standard location but the user may
override it at registration (e.g. a non-standard install). Skills are delivered
to ``<config_dir>/skills`` — there is no separate skill-dir concept.
"""

from __future__ import annotations

import pathlib

from pydantic import BaseModel, ConfigDict, field_validator

from coffer.domain.agent.types import AgentType


class AgentConfig(BaseModel):
    """Resource.config payload when kind == 'agent'."""

    model_config = ConfigDict(extra="forbid")

    type: AgentType
    # Optional override of the agent's config directory. ``None`` → the type's
    # standard location (``~/.claude`` / ``~/.codex``). This is the one
    # directory the user chooses; skills go to ``<config_dir>/skills``.
    config_dir: str | None = None
    # NOTE: the agent carries NO skill-delivery policy. Which skills reach this
    # agent is decided entirely on the skill resource (``enabled`` + ``scope``,
    # spec skill-manager FR-012a) — the same single mechanism ``mcp_server`` uses.
    # Per-agent model binding (spec provider-switching amendment 2026-06-22b, E3). The model the
    # agent projects comes from HERE, not the connection: ``model`` →
    # ``ANTHROPIC_MODEL`` / Codex ``model``; ``fast_model`` →
    # ``ANTHROPIC_SMALL_FAST_MODEL`` (anthropic only); ``wire_api`` → the Codex
    # chat/responses choice. All optional — an unbound agent projects no model
    # env, so it runs on its OWN default model (the connection carries none).
    model: str | None = None
    fast_model: str | None = None
    # Validated against the allowed Codex wire-api values (see _validate_wire_api)
    # so a bad value is a 422 at PATCH time, not a corrupt projected Codex config.
    wire_api: str | None = None

    @field_validator("wire_api")
    @classmethod
    def _validate_wire_api(cls, v: str | None) -> str | None:
        if v is not None and v not in ("chat", "responses"):
            raise ValueError("wire_api must be 'chat' or 'responses'")
        return v

    @field_validator("config_dir")
    @classmethod
    def _validate_config_dir_well_formed(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("config_dir must not be empty if provided")
        path = pathlib.Path(v).expanduser()
        # Well-formedness only; existence + writability is an I/O concern
        # checked in the application layer.
        if not path.is_absolute():
            raise ValueError(f"config_dir must be an absolute path, got {v!r}")
        return str(path)

    def resolved_config_dir(self) -> pathlib.Path:
        """Effective config dir — the user override or the type's standard."""
        if self.config_dir is None:
            return self.type.config_dir()
        return pathlib.Path(self.config_dir)

    def resolved_skill_dir(self) -> pathlib.Path:
        """Where folder-mode skills are delivered: ``<config_dir>/<subpath>``.

        The subpath comes from the agent's capability descriptor — ``skills``
        for Claude Code and Codex. Non-folder delivery modes do not use this
        path.
        """
        from coffer.domain.agent.descriptor import descriptor_for

        return self.resolved_config_dir() / descriptor_for(self.type).skill_subpath
