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


# Each remedy names an action that exists: per-(skill, agent) enable/disable
# is gone (spec skill-manager), and repair re-links only missing/tampered
# links — it never touches foreign content (spec skill-manager "Repair
# repairable drift from master"). Backticked ``coffer ...`` commands are
# resolved against the real CLI by tests/unit/domain/test_skill_drift_remedies.
_REMEDIES: dict[DriftKind, str] = {
    DriftKind.MISSING_LINK: (
        "Run `coffer skill verify --fix` (or `coffer daemon restart`) to re-link it from master."
    ),
    DriftKind.TAMPERED_LINK: (
        "Run `coffer skill verify --fix` (or `coffer daemon restart`) to point the link "
        "back at master."
    ),
    DriftKind.REPLACED_WITH_REGULAR: (
        "A non-Coffer file or folder occupies the target path and Coffer will not touch it; "
        "move it away yourself, then run `coffer skill verify --fix`."
    ),
    DriftKind.MISSING_MASTER: (
        "The master folder is gone; remove the record with `coffer skill rm <name>` "
        "and re-import the skill with `coffer skill import <path>`."
    ),
    DriftKind.ORPHAN_MASTER: (
        "A folder in Coffer's skill store has no Coffer record; move it out of the store "
        "and adopt it with `coffer skill import <path>`, or delete it."
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
