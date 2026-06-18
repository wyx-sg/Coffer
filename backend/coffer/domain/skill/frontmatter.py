"""Pydantic model for the SKILL.md frontmatter (agentskills.io).

The agentskills.io standard requires `name` and `description`: `name` is capped
at 64 chars (lowercase alphanumerics, hyphen, underscore) and `description` at
1024 chars. The optional fields `license` and the experimental `allowed-tools`
are recognized and retained; every other extra field is tolerated
(`extra="allow"`) so non-Coffer-authored skills validate cleanly. Coffer does
not act on a skill's body — the agent that loads it does — but `allowed-tools`
is parsed and retained for the skill trust layer to consume.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Capped at 64 chars to match the master store's folder-name limit
# (``master_store._NAME_MAX_LEN``). A longer name would pass schema validation
# here but then trip a bare ``ValueError`` inside ``copy_in`` → 500; aligning
# the cap turns it into a clean ``SkillValidationError`` (422) at validate time.
# Coffer accepts a documented superset of the agentskills.io name charset: the
# standard allows lowercase letters, digits, and hyphens, and Coffer also
# tolerates underscores for backward-compatibility with skills already on disk.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

# agentskills.io caps the description at 1024 chars. Aligning the cap turns an
# over-long description into a clean ``SkillValidationError`` (422) at validate
# time instead of silently letting an out-of-spec skill into the master store.
_DESCRIPTION_MAX = 1024


class SkillFrontmatter(BaseModel):
    """The frontmatter block at the top of `SKILL.md`."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=_DESCRIPTION_MAX)
    license: str | None = None
    allowed_tools: list[str] | None = Field(default=None, alias="allowed-tools")

    @field_validator("license", mode="before")
    @classmethod
    def _coerce_license(cls, v: Any) -> str | None:
        """Tolerate any scalar `license` value by stringifying it.

        YAML parses an unquoted scalar by type, so `license: 2024` (int),
        `license: true` (bool), or `license: 1.0` (float) would otherwise
        reject the whole skill under a strict `str`. Recognizing optional
        fields is additive (FR-027), so coerce scalars to a string and
        tolerate any non-scalar shape as absent rather than failing.
        """
        if v is None:
            return None
        if isinstance(v, str):
            return v
        if isinstance(v, (int, float, bool)):
            return str(v)
        return None

    @field_validator("name")
    @classmethod
    def _name_pattern(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError(
                "name must match ^[a-z0-9][a-z0-9_-]{0,63}$ "
                "(lowercase letters, digits, hyphen, underscore)"
            )
        return v

    @field_validator("allowed_tools", mode="before")
    @classmethod
    def _coerce_allowed_tools(cls, v: Any) -> list[str] | None:
        """Normalize the experimental `allowed-tools` field to a list of names.

        The field is experimental and third-party authored, so be lenient:
        accept a YAML list or a comma/whitespace-separated string, drop blanks,
        and tolerate any other shape by returning ``None`` rather than rejecting
        an otherwise-valid skill.
        """
        if v is None:
            return None
        if isinstance(v, str):
            parts = [p.strip() for p in re.split(r"[,\s]+", v)]
            return [p for p in parts if p] or None
        if isinstance(v, (list, tuple)):
            normalized = [str(p).strip() for p in v]
            return [p for p in normalized if p] or None
        return None
