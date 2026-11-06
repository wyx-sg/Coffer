"""One row per command across skills, and its problem-first status."""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.domain.skill.cli_status import (
    CliStatus,
    ProbeResult,
    SkillRequirements,
    aggregate,
    status_of,
    version_unverifiable,
)
from coffer.domain.skill.requirements import CommandRequirement

T0 = datetime(2026, 9, 30, tzinfo=UTC)


def _skill(name: str, *reqs: CommandRequirement) -> SkillRequirements:
    return SkillRequirements(skill_uid=f"uid-{name}", skill_name=name, requirements=reqs)


def test_rows_take_the_highest_minimum_and_the_first_skill_by_name() -> None:
    rows = aggregate(
        [
            _skill("zeta", CommandRequirement("gh", title="Z", min_version="2.40")),
            _skill("alpha", CommandRequirement("gh", min_version="2.20")),
            _skill("alpha2", CommandRequirement("jq")),
        ]
    )
    assert [r.command for r in rows] == ["gh", "jq"]
    gh = rows[0]
    assert gh.min_version == "2.40"
    assert gh.title == "Z"  # only zeta gives a title
    assert [(n.skill_name, n.min_version) for n in gh.needed_by] == [
        ("alpha", "2.20"),
        ("zeta", "2.40"),
    ]


def _probe(path: str | None, version: str | None) -> ProbeResult:
    return ProbeResult(path=path, version=version, checked_at=T0)


def test_status_order_of_checks() -> None:
    [row] = aggregate([_skill("s", CommandRequirement("gh", min_version="2.40"))])
    assert status_of(row, _probe(None, None)) is CliStatus.MISSING
    assert status_of(row, _probe("/b/gh", "2.30.0")) is CliStatus.OUTDATED
    assert status_of(row, _probe("/b/gh", "2.41")) is CliStatus.READY


def test_an_unreadable_version_is_not_outdated_but_cannot_be_verified() -> None:
    [row] = aggregate([_skill("s", CommandRequirement("go", min_version="1.22"))])
    probe = _probe("/b/go", None)
    assert status_of(row, probe) is CliStatus.READY
    assert version_unverifiable(row, probe) is True


def test_a_version_is_verifiable_when_read_or_when_no_minimum_is_asked() -> None:
    [with_min] = aggregate([_skill("s", CommandRequirement("gh", min_version="2.40"))])
    [no_min] = aggregate([_skill("s", CommandRequirement("jq"))])
    assert version_unverifiable(with_min, _probe("/b/gh", "2.41")) is False
    assert version_unverifiable(with_min, _probe(None, None)) is False
    assert version_unverifiable(no_min, _probe("/b/jq", None)) is False
