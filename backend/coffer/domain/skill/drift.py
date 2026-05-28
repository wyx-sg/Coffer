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
    """One row in the drift report."""

    skill_name: str
    agent_name: str
    kind: DriftKind
    target_path: str
    suggested_remedy: str


@dataclass
class DriftReport:
    """Output of `SkillService.verify()`."""

    entries: list[DriftEntry] = field(default_factory=list)

    @property
    def has_drift(self) -> bool:
        return bool(self.entries)
