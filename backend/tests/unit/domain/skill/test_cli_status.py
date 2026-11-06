"""One row per command across skills, and its problem-first status."""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.domain.skill.cli_status import (
    CliStatus,
    ProbeResult,
    SkillRequirements,
    aggregate,
    status_of,
)
from coffer.domain.skill.requirements import CommandRequirement

T0 = datetime(2026, 9, 30, tzinfo=UTC)


def _skill(name: str, *reqs: CommandRequirement) -> SkillRequirements:
    return SkillRequirements(skill_uid=f"uid-{name}", skill_name=name, requirements=reqs)


def test_rows_take_the_first_title_and_list_every_skill_by_name() -> None:
    rows = aggregate(
        [
            _skill("zeta", CommandRequirement("gh", title="Z", why="Labels issues.")),
            _skill("alpha", CommandRequirement("gh")),
            _skill("alpha2", CommandRequirement("jq")),
        ]
    )
    assert [r.command for r in rows] == ["gh", "jq"]
    gh = rows[0]
    assert gh.title == "Z"  # only zeta gives a title
    assert [(n.skill_name, n.why) for n in gh.needed_by] == [
        ("alpha", None),
        ("zeta", "Labels issues."),
    ]


def test_a_command_is_missing_or_ready_by_whether_it_is_found() -> None:
    assert status_of(ProbeResult(None, T0)) is CliStatus.MISSING
    assert status_of(ProbeResult("/b/gh", T0)) is CliStatus.READY
