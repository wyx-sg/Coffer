"""`SkillConfig` — Pydantic schema stored on `Resource.config` for kind=skill."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from coffer.domain.skill.source import SkillSource

#: The longest description a skill's resource keeps (agentskills.io's cap).
DESCRIPTION_STORED_MAX = 1024


def stored_description(text: str) -> str:
    """``text`` as the resource keeps it: at most ``DESCRIPTION_STORED_MAX`` chars."""
    if len(text) <= DESCRIPTION_STORED_MAX:
        return text
    return text[: DESCRIPTION_STORED_MAX - 1].rstrip() + "…"


class SkillConfig(BaseModel):
    """Resource.config payload when kind == 'skill'."""

    model_config = ConfigDict(extra="forbid")

    source: SkillSource
    # There is deliberately NO ``skill_md_name``. It used to mirror the
    # SKILL.md frontmatter's ``name``, which is also where the resource's own
    # name comes from — so it was a second spelling of ``Resource.name``, with
    # no reader anywhere and two places to disagree once renaming existed
    # (ADR identity-is-the-uid-inside-the-file).
    # The skill's name is ``Resource.name``; ask the row.
    #
    # The SKILL.md description, cut to the agentskills.io cap of 1024 chars
    # (``stored_description``): SKILL.md itself may run longer, and every
    # Coffer that reads this file — on any synced machine — keeps the cap.
    skill_md_description: str = Field(min_length=1, max_length=DESCRIPTION_STORED_MAX)
    version_hash: str = Field(min_length=1, max_length=128)
    last_synced_from_source_at: datetime | None = None
