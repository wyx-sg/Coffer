"""Where a skill is inside something a person hands Coffer.

One rule for an archive, a Git repository's subpath and a staged folder
(spec skill-manager "Add skills from an archive"): a folder is a skill when
``SKILL.md`` sits at its top. If the root holds one, the root is the skill and
its subfolders are part of it; otherwise every direct child folder that holds
one is a skill; otherwise there is none, and the answer says both places were
looked at. Two levels down is deliberately not searched: a skill buried in a
tree is usually a repository's example or test fixture, not something the
person meant to add.

Like ``validator.py`` this reads the filesystem it is pointed at (a staging
directory Coffer owns) with the stdlib only.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

#: Folders an archiver or a checkout adds that are never a skill.
_SKIPPED = frozenset({"__MACOSX", ".git"})

#: The reason code a stage answers with when neither place holds a SKILL.md.
NO_SKILL_MD = "skill_md_not_found"


@dataclass(frozen=True)
class Discovery:
    """The skill folders found under ``root``, as paths relative to it.

    ``"."`` is the root itself. Empty means none was found.
    """

    root: pathlib.Path
    folders: tuple[str, ...]


def find_skill_folders(root: pathlib.Path) -> Discovery:
    """The skill folders at ``root`` or one level below it, sorted by name."""
    if (root / "SKILL.md").is_file():
        return Discovery(root, (".",))
    found: list[str] = []
    if root.is_dir():
        for child in sorted(root.iterdir(), key=lambda p: p.name):
            if child.name.startswith(".") or child.name in _SKIPPED:
                continue
            if child.is_symlink() or not child.is_dir():
                continue
            if (child / "SKILL.md").is_file():
                found.append(child.name)
    return Discovery(root, tuple(found))


def looked_in(label: str) -> dict[str, object]:
    """The details of a NO_SKILL_MD refusal: where a SKILL.md was looked for."""
    return {
        "looked_in": [f"{label}/SKILL.md", f"{label}/<folder>/SKILL.md"],
        "hint": "SKILL.md must be at the top or one folder down",
    }


__all__ = ["NO_SKILL_MD", "Discovery", "find_skill_folders", "looked_in"]
