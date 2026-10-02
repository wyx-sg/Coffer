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


@dataclass
class DriftEntry:
    """One row in the drift report.

    Carries both the labels a person reads and the uids a repair addresses.
    They are not two spellings of one thing: the names are what the report
    SAYS, and the uids are what a repair re-delivers against, so a
    skill renamed between the verify pass and the repair pass is still the
    skill that gets repaired (ADR identity-is-the-uid-inside-the-file).

    Both uids are ``None`` for an ORPHAN_MASTER entry, which is a folder on
    disk that no resource row claims — there is no identity to record, and
    nothing for a repair to address, which is why a repair skips that
    kind outright.

    It carries no remedy text: what to do about a kind is said by each surface
    in its own words (spec skill-manager "Report skill drift on request").
    """

    skill_name: str
    agent_name: str
    kind: DriftKind
    target_path: str
    skill_uid: str | None = None
    agent_uid: str | None = None
    #: The prompt that hands a finding no repair settles to an agent
    #: (``application/skill/drift_handoff.py``); ``None`` when Repair is the
    #: fix. What a person reads about the kind is each surface's own words:
    #: the web UI translates ``kind``, the CLI names its own commands.
    handoff: str | None = None


@dataclass
class DriftReport:
    """Output of `coffer skill verify` (``drift_view.verify``)."""

    entries: list[DriftEntry] = field(default_factory=list)


@dataclass(frozen=True)
class RepairResult:
    """Output of `coffer skill verify --fix` (``drift_view.repair``).

    ``remediated`` holds entries that were successfully re-delivered;
    ``remaining`` is the residual DriftReport after the repair pass (entries
    that could not be repaired or were intentionally skipped).
    """

    remediated: list[DriftEntry]
    remaining: DriftReport
