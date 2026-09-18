"""`SkillConfig` — Pydantic schema stored on `Resource.config` for kind=skill."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from coffer.domain.skill.source import SkillSource


class SkillConfig(BaseModel):
    """Resource.config payload when kind == 'skill'."""

    model_config = ConfigDict(extra="forbid")

    source: SkillSource
    # There is deliberately NO ``skill_md_name``. It used to mirror the
    # SKILL.md frontmatter's ``name``, which is also where the resource's own
    # name comes from — so it was a second spelling of ``Resource.name``, with
    # no reader anywhere and two places to disagree once renaming existed
    # (ADR resource-identity-is-an-immutable-uid). Migration 0098 strips it.
    # The skill's name is ``Resource.name``; ask the row.
    #
    # Capped at 1024 to match the SKILL.md frontmatter ``description`` cap
    # (see ``frontmatter._DESCRIPTION_MAX``).
    skill_md_description: str = Field(min_length=1, max_length=1024)
    version_hash: str = Field(min_length=1, max_length=128)
    last_synced_from_source_at: datetime | None = None
