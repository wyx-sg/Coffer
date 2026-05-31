"""`SkillConfig` — Pydantic schema stored on `Resource.config` for kind=skill."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from coffer.domain.skill.source import SkillSource


class SkillConfig(BaseModel):
    """Resource.config payload when kind == 'skill'."""

    model_config = ConfigDict(extra="forbid")

    source: SkillSource
    # Capped at 64 to match the master store folder-name limit and the
    # SKILL.md frontmatter ``name`` cap (see ``frontmatter._NAME_RE``).
    skill_md_name: str = Field(min_length=1, max_length=64)
    skill_md_description: str = Field(min_length=1)
    version_hash: str = Field(min_length=1, max_length=128)
    last_synced_from_source_at: datetime | None = None
