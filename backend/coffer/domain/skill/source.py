"""Records a skill's provenance.

``local_import``: file copied from a path on disk; retained for informational
purposes.

``archive_import``: unpacked from an uploaded archive; the archive's file name
and the folder inside it are informational.

``git_import``: copied from a folder of a Git repository at one pinned commit,
which is what an update check compares the ref's newer commits against.

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


class ArchiveImportSource(BaseModel):
    """A skill unpacked from an uploaded ``.zip`` / ``.skill`` archive.

    ``folder`` is where inside the archive the skill's ``SKILL.md`` sat —
    ``""`` for the archive's top, a folder name when it was one level down
    (spec skill-manager "Add skills from an archive"). Informational, like a
    local import's path: there is nothing to re-fetch.
    """

    type: Literal["archive_import"] = "archive_import"
    archive_name: str = Field(min_length=1)
    folder: str = ""


class GitImportSource(BaseModel):
    """A skill copied from a folder of a Git repository, pinned to one commit.

    ``ref`` is what the user asked for (``None`` = the default branch), kept so
    an update check follows the same branch or tag. ``subpath`` is the skill's
    own folder inside the repository ("" for the repository's top) — resolved
    after discovery, so a check looks at exactly the files this skill holds.
    ``content_hash`` is the folder's content at ``commit``
    (``domain.skill.content_hash``): the master folder differing from it is
    what "edited locally since the pin" means (spec skill-manager "Hand a
    Git-imported skill's update to an agent").
    """

    type: Literal["git_import"] = "git_import"
    url: str = Field(min_length=1)
    ref: str | None = None
    subpath: str = ""
    commit: str = Field(min_length=7, max_length=64)
    content_hash: str = Field(min_length=1, max_length=128)


class BuiltinSource(BaseModel):
    """Coffer's own generated skill — no provenance beyond the name."""

    type: Literal["builtin"] = "builtin"


SkillSource = Annotated[
    LocalImportSource | ArchiveImportSource | GitImportSource | BuiltinSource,
    Field(discriminator="type"),
]

#: The variants a person adds; ``builtin`` is Coffer's own.
ImportedSource = LocalImportSource | ArchiveImportSource | GitImportSource
