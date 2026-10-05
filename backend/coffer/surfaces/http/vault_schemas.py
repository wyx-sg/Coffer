"""Wire shapes of ``/api/v1/vault``: the hand edits validation refused (spec
vault-storage "List the hand edits the vault kept out") and the restore
hand-off ("Hand restoring an earlier version of a vault file to an agent")."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from coffer.domain.vault.findings import Finding
from coffer.surfaces.http.handoff_schemas import HandoffOut


class VaultProblemOut(BaseModel):
    """A hand edit validation refused: on disk, uncommitted, not in effect."""

    path: str
    code: str
    message: str
    #: The resource the file is about, when it names one.
    uid: str | None
    #: ``error`` (kept out of ``HEAD``) or ``warning``.
    severity: str


class VaultProblemsOut(BaseModel):
    problems: list[VaultProblemOut]


class VaultHistoryHandoffIn(BaseModel):
    #: A vault-relative file, or a folder ending in ``/``.
    path: str = Field(min_length=1)
    #: Bring the path back to how it was at this time; omit to have the agent
    #: list the recent versions and ask which one.
    at: datetime | None = None


class VaultHistoryHandoffOut(BaseModel):
    #: The file or folder (ending in ``/``) the hand-off is about.
    path: str
    #: Where that path is on this machine, for Reveal in Finder.
    absolute_path: str
    #: The vault's own absolute path.
    vault_path: str
    #: ``git -C <vault> log -p -- <path>``, ready to copy.
    log_command: str
    handoff: HandoffOut


def problem_out(finding: Finding) -> VaultProblemOut:
    return VaultProblemOut(
        path=finding.path,
        code=finding.code.value,
        message=finding.message,
        uid=finding.uid,
        severity=finding.severity.value,
    )


__all__ = [
    "VaultHistoryHandoffIn",
    "VaultHistoryHandoffOut",
    "VaultProblemOut",
    "VaultProblemsOut",
    "problem_out",
]
