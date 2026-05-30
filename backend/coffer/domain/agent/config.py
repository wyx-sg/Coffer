"""`AgentConfig` — Pydantic schema stored on `Resource.config` for kind=agent.

Validation here is *value-level only* (types, ranges, well-formedness). Path
writability is asserted at registration time in `application/agent/service`
because it is an I/O check and domain stays pure.
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
    skill_dir: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _drop_legacy_auto_detected(cls, data: Any) -> Any:
        """Legacy tolerance: older rows persisted config JSON carrying an
        ``auto_detected`` flag (since removed — detection is confirm-based and
        registers like a manual add). ``extra="forbid"`` would reject those
        rows on load, so we strip the dead key from dict input before
        validation. Genuinely-unknown fields are still rejected.
        """
        if isinstance(data, dict) and "auto_detected" in data:
            data = {k: v for k, v in data.items() if k != "auto_detected"}
        return data

    @field_validator("skill_dir")
    @classmethod
    def _validate_skill_dir_well_formed(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("skill_dir must not be empty if provided")
        path = pathlib.Path(v).expanduser()
        # We resolve only well-formedness here; existence + writability is
        # checked in the application layer because it's an I/O concern.
        if not path.is_absolute():
            raise ValueError(f"skill_dir must be an absolute path, got {v!r}")
        return str(path)

    def resolved_skill_dir(self) -> pathlib.Path:
        """Effective skill_dir — override or type default."""
        if self.skill_dir is None:
            return self.type.default_skill_dir()
        return pathlib.Path(self.skill_dir)
