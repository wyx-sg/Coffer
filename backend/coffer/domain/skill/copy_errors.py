"""Errors of resolving an agent's copy of a skill, and of the skills store's
orphan folders (spec skill-manager "Resolve a folder in the way of a skill's
link", "Refuse deleting a skill whose copy Coffer did not make", "Act on a
folder in the skills store that no skill claims")."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class SkillCopyNotOurs(CofferError):  # noqa: N818
    """Deleting a skill found an agent's copy that is not Coffer's link.

    Removing the skill would leave that folder behind, or delete files Coffer
    did not make, so the whole delete is refused and nothing changes. The
    envelope names the folder and the agent.
    """

    code = "SKILL_COPY_NOT_OURS"

    def __init__(self, skill_name: str, path: str, agent_name: str) -> None:
        super().__init__(
            f"{path} is no longer a Coffer link, so Coffer won't remove it; restore it from "
            f"master first, or delete that folder yourself. Nothing of {skill_name} was changed."
        )
        self.error_details = {"path": path, "agent_name": agent_name}


class SkillCopyNotDiffering(CofferError):  # noqa: N818
    """Compare or resolve was asked for a copy that is not a folder in the way:
    the agent's path holds Coffer's link, or nothing at all."""

    code = "SKILL_COPY_NOT_DIFFERING"

    def __init__(self, skill_name: str, agent_name: str) -> None:
        super().__init__(
            f"{agent_name}'s copy of {skill_name} is not a folder in the way of Coffer's link; "
            "there is nothing to compare or resolve"
        )
        self.error_details = {"agent_name": agent_name}


class SkillOrphanNotFound(CofferError):  # noqa: N818
    """No folder by that name in the skills store is unclaimed."""

    code = "SKILL_ORPHAN_NOT_FOUND"

    def __init__(self, name: str) -> None:
        super().__init__(f"no folder named {name!r} in the skills store is outside your library")
        self.error_details = {"name": name}


__all__ = ["SkillCopyNotDiffering", "SkillCopyNotOurs", "SkillOrphanNotFound"]
