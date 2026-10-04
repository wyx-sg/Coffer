"""The hand-offs for the skill drift a person has to settle.

Spec skill-manager "Hand unsettled skill drift to an agent with a prompt".
Three drift kinds are never repaired by a pass, because repairing them would
mean choosing between two versions or deciding what a folder is: a folder
Coffer did not make sitting where a skill's link belongs, a folder in the
skills store no skill owns, and a skill whose master folder is gone. Coffer
keeps its buttons for them (the compare and its two choices, Add to library /
Delete folder, Remove the skill) and hands the looking to the person's agent:
compare, say what the folder is, find a copy that can be restored. The agent
reads and advises; the choice stays a button the person presses, except the
one write that has no button — copying a found master back into place.

Built only from what the drift finding itself carries (the skill's name, the
path, the master path), so the drift report and the attention list hand over
the same words.
"""

from __future__ import annotations

import pathlib

from coffer.domain.handoff import Handoff, render_handoff
from coffer.domain.skill.drift import DriftKind

#: Asked of every agent these prompts reach.
_HANDS_OFF = "Do not move, delete or edit any folder yourself; I press the button in Coffer."


def foreign_folder_handoff(*, skill: str, folder: str, master: str, backup: pathlib.Path) -> str:
    return render_handoff(
        Handoff(
            task=(
                f"{folder} is a folder Coffer didn't make, sitting where Coffer links skill "
                f"{skill} into an agent's skills folder, so Coffer leaves it alone. Compare it "
                "with Coffer's copy and tell me which one to keep."
            ),
            facts=(
                f"Skill: {skill}",
                f"Folder in the way: {folder}",
                f"Coffer's copy (the skill's master folder): {master}",
                "In Coffer I choose one of two: Replace it with Coffer's link (the folder is "
                f"moved to {backup}/<agent>/ first, nothing is lost) or Adopt this folder (its "
                "files become the master, so every agent with the skill gets them).",
            ),
            steps=(
                "Compare the two folders file by file; only read them.",
                "Tell me whether the folder in the way holds edits worth keeping — newer than "
                "Coffer's copy, or changes Coffer's copy lacks — and name the files.",
                "Recommend Adopt this folder or Replace it with Coffer's link, and say why; if "
                "each side has something the other lacks, say what, and let me decide.",
                _HANDS_OFF,
            ),
        )
    )


def orphan_master_handoff(*, name: str, folder: str, backup: pathlib.Path) -> str:
    return render_handoff(
        Handoff(
            task=(
                f"{folder} is a folder in Coffer's skills store that no skill in my library owns, "
                "so no agent gets it. Look at it and tell me whether to add it to my library or "
                "delete it."
            ),
            facts=(
                f"Folder: {folder}",
                f"Coffer's skills store: {pathlib.Path(folder).parent}",
                "In Coffer I choose one of two: Add to library (registers the folder in place; "
                f"its SKILL.md must name it {name}) or Delete folder (moved to {backup}/orphans/, "
                "not deleted).",
                "The skills already in my library are the other folders in that store.",
            ),
            steps=(
                "Read the folder: say what the skill does and whether its SKILL.md is valid and "
                f"its frontmatter `name` is {name}.",
                "Check whether a skill already in my library covers the same thing.",
                "Recommend Add to library or Delete folder, and say why.",
                _HANDS_OFF,
            ),
        )
    )


def missing_master_handoff(*, skill: str, master: str, backup: pathlib.Path) -> str:
    return render_handoff(
        Handoff(
            task=(
                f"Skill {skill}'s master folder {master} is gone, so Coffer has nothing to link "
                "into my agents. Find out whether it can be recovered."
            ),
            facts=(
                f"Skill: {skill}",
                f"Where its master folder belongs: {master}",
                f"Folders Coffer set aside are under {backup}/ (per agent, and orphans/), named "
                f"{skill}-<time>.",
                "The skill's page in Coffer shows where it came from (its source: a Git "
                "repository, a folder or an archive); ask me if you need it.",
                "An agent's skills folder may still hold a copied (not linked) copy of it.",
                "The master folder is in Coffer's vault, whose history keeps its earlier "
                "versions: Restore on the skill's Files tab in Coffer puts back the newest "
                "version that still had files.",
            ),
            steps=(
                "Look for a copy: in those backups, in the agents' skills folders and at the "
                "skill's source; only read.",
                "Tell me what you found, which copy is the newest — Coffer's own restore "
                "included — and whether it is complete "
                f"(a SKILL.md whose `name` is {skill}).",
                f"Once I agree, copy (don't move) that copy to {master}; Coffer links it to the "
                "agents again on its next pass. If nothing can be recovered, say so, and I will "
                "remove the skill in Coffer.",
                "Do not delete anything.",
            ),
        )
    )


def drift_handoff(
    kind: DriftKind, *, skill: str, path: str, master: str, backup: pathlib.Path
) -> str | None:
    """The hand-off for one drift finding, or ``None`` when Repair is the fix.

    ``path`` is where the finding is (the link path; for an orphan, its
    folder); ``master`` is the skill's master folder (for an orphan, its folder
    again); ``backup`` is where set-aside folders go
    (``MasterStorePort.backup_root``, class ``content`` — not beside the
    master, which lives in the vault).
    """
    if kind is DriftKind.REPLACED_WITH_REGULAR:
        return foreign_folder_handoff(skill=skill, folder=path, master=master, backup=backup)
    if kind is DriftKind.ORPHAN_MASTER:
        return orphan_master_handoff(name=skill, folder=path, backup=backup)
    if kind is DriftKind.MISSING_MASTER:
        return missing_master_handoff(skill=skill, master=master, backup=backup)
    return None


__all__ = [
    "drift_handoff",
    "foreign_folder_handoff",
    "missing_master_handoff",
    "orphan_master_handoff",
]
