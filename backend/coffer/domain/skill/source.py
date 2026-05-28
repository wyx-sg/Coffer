"""Discriminated union recording a skill's provenance.

`local_import`: file copied from a path on disk; only retained for
informational purposes.

`git`: shallow-cloned from a public Git URL with a ref and optional subpath.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Discriminator, Field, HttpUrl


class LocalImportSource(BaseModel):
    type: Literal["local_import"] = "local_import"
    original_path: str = Field(min_length=1)


class GitSource(BaseModel):
    type: Literal["git"] = "git"
    git_url: HttpUrl
    git_ref: str = Field(min_length=1, max_length=200)
    git_subpath: str = ""


SkillSource = Annotated[
    LocalImportSource | GitSource,
    Discriminator("type"),
]
