"""Drift between persisted bindings and on-disk symlinks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class DriftKind(StrEnum):
    """Categorical disagreement between a binding row and its disk target."""

    MISSING_LINK = "missing_link"
    TAMPERED_LINK = "tampered_link"
    REPLACED_WITH_REGULAR = "replaced_with_regular"
    MISSING_MASTER = "missing_master"
    ORPHAN_MASTER = "orphan_master"


_REMEDIES: dict[DriftKind, str] = {
    DriftKind.MISSING_LINK: "Re-enable the skill for this agent to recreate the link.",
    DriftKind.TAMPERED_LINK: (
        "Disable then re-enable the skill for this agent, or pass --force to overwrite."
    ),
    DriftKind.REPLACED_WITH_REGULAR: (
        "A non-Coffer file or directory occupies the target path; "
        "pass --force to back it up and re-link."
    ),
    DriftKind.MISSING_MASTER: "Re-import or re-fetch the skill; the master folder is gone.",
    DriftKind.ORPHAN_MASTER: (
        "Master folder on disk has no Coffer record; adopt it via import or remove it manually."
    ),
}


def suggested_remedy(kind: DriftKind) -> str:
    return _REMEDIES[kind]


@dataclass
class DriftEntry:
    """One row in the drift report.

    Carries both the labels a person reads and the uids a repair addresses.
    They are not two spellings of one thing: the names are what the report
    SAYS, and the uids are what ``repair_drift`` re-delivers against, so a
    skill renamed between the verify pass and the repair pass is still the
    skill that gets repaired (ADR resource-identity-is-an-immutable-uid).

    Both uids are ``None`` for an ORPHAN_MASTER entry, which is a folder on
    disk that no resource row claims — there is no identity to record, and
    nothing for a repair to address, which is why ``repair_drift`` skips that
    kind outright.
    """

    skill_name: str
    agent_name: str
    kind: DriftKind
    target_path: str
    suggested_remedy: str
    skill_uid: str | None = None
    agent_uid: str | None = None


@dataclass
class DriftReport:
    """Output of `SkillService.verify()`."""

    entries: list[DriftEntry] = field(default_factory=list)


@dataclass(frozen=True)
class RepairResult:
    """Output of `SkillService.repair_drift()`.

    ``remediated`` holds entries that were successfully re-delivered;
    ``remaining`` is the residual DriftReport after the repair pass (entries
    that could not be repaired or were intentionally skipped).
    """

    remediated: list[DriftEntry]
    remaining: DriftReport
