"""Records a skill's provenance.

``local_import``: file copied from a path on disk; retained for informational
purposes.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LocalImportSource(BaseModel):
    type: Literal["local_import"] = "local_import"
    original_path: str = Field(min_length=1)


SkillSource = LocalImportSource
