"""Pydantic model for the SKILL.md frontmatter (agentskills.io minimum).

Only `name` and `description` are required by the standard. Extra fields are
tolerated so non-Coffer-authored skills validate cleanly. Coffer does not
attempt to interpret them; the agent that loads the skill does.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Capped at 64 chars to match the master store's folder-name limit
# (``master_store._NAME_MAX_LEN``). A longer name would pass schema validation
# here but then trip a bare ``ValueError`` inside ``copy_in`` → 500; aligning
# the cap turns it into a clean ``SkillValidationError`` (422) at validate time.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class SkillFrontmatter(BaseModel):
    """The frontmatter block at the top of `SKILL.md`."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def _name_pattern(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError(
                "name must match ^[a-z0-9][a-z0-9_-]{0,63}$ "
                "(lowercase letters, digits, hyphen, underscore)"
            )
        return v
