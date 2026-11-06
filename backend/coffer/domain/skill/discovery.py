"""Where a skill is inside something a person hands Coffer.

One rule for an archive, a Git repository's subpath and a staged folder
(spec skill-manager "Add skills from an archive"): a folder is a skill when
``SKILL.md`` sits at its top, and everything under it is part of that skill.
If the root holds one, the root is the skill; otherwise every folder below it
that holds one is a skill, searched down to ``MAX_DEPTH`` levels, so a
collection that keeps its skills in ``skills/<name>/`` (anthropics/skills) or
``skills/.curated/<name>/`` (openai/skills) is found from the repository's top,
as Codex itself finds skills. Every skill found is listed and the person picks
which to add, so an example or a test fixture deep in a tree is shown, never
added on its own.

Like ``validator.py`` this reads the filesystem it is pointed at (a staging
directory Coffer owns) with the stdlib only.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

#: Folders an archiver, a checkout or a package manager adds that never hold
#: a skill. Other dot-folders are searched: openai/skills keeps its skills in
#: ``skills/.curated/``.
_SKIPPED = frozenset({"__MACOSX", ".git", ".github", "node_modules"})

#: How many folder levels below the root are searched.
MAX_DEPTH = 4

#: The most skills one search lists.
MAX_FOUND = 500

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
    """The skill folders at ``root`` or below it, sorted by path.

    A folder holding ``SKILL.md`` is not searched further: its subfolders are
    part of that skill. Links are not followed.
    """
    if (root / "SKILL.md").is_file():
        return Discovery(root, (".",))
    found: list[str] = []

    def walk(folder: pathlib.Path, depth: int) -> None:
        if depth > MAX_DEPTH or len(found) >= MAX_FOUND:
            return
        try:
            children = sorted(folder.iterdir(), key=lambda p: p.name)
        except OSError:
            return
        for child in children:
            if child.name in _SKIPPED or child.is_symlink() or not child.is_dir():
                continue
            if (child / "SKILL.md").is_file():
                found.append(child.relative_to(root).as_posix())
                if len(found) >= MAX_FOUND:
                    return
            else:
                walk(child, depth + 1)

    if root.is_dir():
        walk(root, 1)
    return Discovery(root, tuple(sorted(found)))


def looked_in(label: str) -> dict[str, object]:
    """The details of a NO_SKILL_MD refusal: where a SKILL.md was looked for."""
    return {
        "looked_in": [f"{label}/SKILL.md", f"{label}/**/SKILL.md"],
        "hint": f"no SKILL.md at the top or in the folders below it (up to {MAX_DEPTH} levels)",
    }


__all__ = ["MAX_DEPTH", "MAX_FOUND", "NO_SKILL_MD", "Discovery", "find_skill_folders", "looked_in"]
