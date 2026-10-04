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
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

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
    # spec skill-manager "Deliver a skill only where it is enabled and in
    # scope") — the same single mechanism ``mcp_server`` uses.
    # Per-agent model binding (spec provider-switching "Take projected model
    # keys from the agent's binding"). The model the agent projects comes from
    # HERE, not the connection: ``model`` → Claude Code's top-level ``model``
    # settings key / Codex's ``model``; ``tier_models`` →
    # Claude Code's ``ANTHROPIC_DEFAULT_<TIER>_MODEL`` pins (the Haiku pin also
    # runs its background tasks). All optional — an unbound agent projects no
    # model key, so it runs on its OWN default model (the connection carries none).
    model: str | None = None
    tier_models: dict[str, str] | None = None
    # The provider connection this agent runs on (spec agent-registry "Carry the
    # connection an agent runs on on the agent record"): the uid of a ``provider``
    # resource, or ``None`` for the agent's own built-in login. Which connection
    # an agent is on is a fact about the AGENT, so at most one per agent holds by
    # construction. It is a bare uid, not checked against the provider table here
    # (domain stays pure, and the connection may be deleted later): one that
    # resolves to no enabled connection reaching this agent means "no connection"
    # (``application.provider.targets.connection_for_agent``).
    connection_uid: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _drop_retired_effort(cls, data: Any) -> Any:
        """Migration for the removal of reasoning effort: a stored agent config
        may still carry ``effort``; drop it (the file loses the key on its next
        write)."""
        if isinstance(data, dict) and "effort" in data:
            return {k: v for k, v in data.items() if k != "effort"}
        return data

    @field_validator("tier_models")
    @classmethod
    def _validate_tiers(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        """Only Claude Code's four tiers, each naming a non-blank model id; an
        empty mapping is no mapping."""
        if v is None:
            return None
        from coffer.domain.agent.tiers import CLAUDE_TIERS

        cleaned: dict[str, str] = {}
        for tier, model in v.items():
            if tier not in CLAUDE_TIERS:
                known = ", ".join(CLAUDE_TIERS)
                raise ValueError(f"unknown tier {tier!r}: expected one of {known}")
            if not isinstance(model, str) or not model.strip():
                raise ValueError(f"tier {tier!r} must name a model")
            cleaned[tier] = model.strip()
        return cleaned or None

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

    def runtime_env(self) -> dict[str, str]:
        """Environment overrides that point the agent's own runtime at this
        agent's config dir — empty for the type's standard location (see
        :func:`coffer.domain.agent.home_env.home_env`)."""
        from coffer.domain.agent.home_env import home_env

        return home_env(self.type, self.resolved_config_dir())

    def resolved_skill_dir(self) -> pathlib.Path:
        """Where folder-mode skills are delivered: ``<config_dir>/<subpath>``.

        The subpath comes from the agent's capability descriptor — ``skills``
        for Claude Code and Codex. Non-folder delivery modes do not use this
        path.
        """
        from coffer.domain.agent.descriptor import descriptor_for

        return self.resolved_config_dir() / descriptor_for(self.type).skill_subpath
