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

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_keys(cls, data: Any) -> Any:
        """Tolerate / migrate keys from older persisted rows that
        ``extra="forbid"`` would otherwise reject on load:

        - ``auto_detected`` — detection is confirm-based now (registers like a
          manual add), so the flag was removed; the dead key is dropped.
        - ``skill_dir`` — superseded by ``config_dir`` (skills now go to
          ``<config_dir>/skills``). Rather than silently drop a user's
          override and revert skill delivery to the type default, MAP it onto
          ``config_dir``: a ``<dir>/skills`` override becomes ``config_dir=<dir>``
          (skills land in the same place); any other custom dir becomes the
          config dir itself (skills land in its ``skills/`` subfolder). The
          0005 migration rewrites rows at rest; this is the load-time safety
          net. Genuinely-unknown fields are still rejected.
        """
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if k != "auto_detected"}
            legacy = data.pop("skill_dir", None)
            if legacy and not data.get("config_dir"):
                p = pathlib.Path(legacy)
                data["config_dir"] = str(p.parent) if p.name == "skills" else legacy
        return data

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
        """Where skills are delivered: ``<config_dir>/skills``."""
        return self.resolved_config_dir() / "skills"
