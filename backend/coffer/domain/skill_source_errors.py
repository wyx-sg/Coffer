"""Errors of skill sources (spec skill-manager "Add skills from an archive",
"Add skills from a Git repository", "Update a Git-imported skill from its
source"). Re-exported from ``coffer.domain.errors``."""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class SkillSourceRejected(CofferError):  # noqa: N818
    """An archive, a folder or a checkout refused before anything is written.

    Same code and status as any invalid skill (``SKILL_INVALID``, 422), with a
    ``reason`` and JSON-safe ``error_details`` the envelope hands over whole —
    the offending archive entries, or where a ``SKILL.md`` was looked for — so
    a surface can name them without parsing the message.
    """

    code = "SKILL_INVALID"

    def __init__(self, reason: str, message: str, details: dict[str, object]) -> None:
        super().__init__(message)
        self.reason = reason
        self.details = details
        self.error_details = details


class SkillStagingNotFound(CofferError):  # noqa: N818
    """A staged source (an import or an update preview) is gone or never was.

    Stages live in the daemon's memory for an hour (spec skill-manager "Add
    skills from an archive"); a confirm after that, or after a restart, finds
    nothing to confirm.
    """

    code = "SKILL_STAGING_NOT_FOUND"

    def __init__(self, staging_id: str) -> None:
        super().__init__(
            f"nothing is staged under {staging_id!r}; it was confirmed, cancelled or expired — "
            "stage the source again"
        )
        self.staging_id = staging_id


class SkillSourceUnreachable(CofferError):  # noqa: N818
    """``git`` could not fetch a skill's repository, resolve its ref or find
    its folder. The message is git's own, with any credential stripped."""

    code = "SKILL_SOURCE_UNREACHABLE"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.git_message = message


class SkillUpdateConflict(CofferError):  # noqa: N818
    """The skill's folder was edited since its pinned commit, so taking the
    update would discard the edit — only an explicit Take theirs does that."""

    code = "SKILL_UPDATE_CONFLICT"

    def __init__(self, name: str) -> None:
        super().__init__(
            f"skill {name} was edited since its pinned commit; keep your edits, or take the "
            "update and discard them"
        )


class SkillNotFromGit(CofferError):  # noqa: N818
    """An update operation on a skill that was not added from a Git repository."""

    code = "SKILL_NOT_FROM_GIT"

    def __init__(self, name: str) -> None:
        super().__init__(
            f"skill {name} was not added from a Git repository, so it has no source to update "
            "from; re-add it with --force to replace it"
        )
