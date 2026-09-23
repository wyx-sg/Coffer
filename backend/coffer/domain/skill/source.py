"""Records a skill's provenance.

``local_import``: file copied from a path on disk; retained for informational
purposes.

``builtin``: Coffer wrote this one itself. It carries no fields at all, and
that is the point — a builtin skill's master folder is regenerated from the
running build and the live knowledge catalogue, so there is nothing about
*where it came from* that would still be true tomorrow. Anything this variant
stored (a path, a timestamp, a build id) would be a fact about one machine,
recorded where nothing reads it.

This discriminator is also what tells the resource framework the row is derived
output: the skill kind reads it (``domain.skill.builtin.is_builtin``) to refuse
a delete, and to declare that this one row does not converge while every other
skill's does (spec vault-sync "Withhold derived output in both halves").
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class LocalImportSource(BaseModel):
    type: Literal["local_import"] = "local_import"
    original_path: str = Field(min_length=1)


class BuiltinSource(BaseModel):
    """Coffer's own generated skill — no provenance beyond the name."""

    type: Literal["builtin"] = "builtin"


SkillSource = Annotated[LocalImportSource | BuiltinSource, Field(discriminator="type")]
