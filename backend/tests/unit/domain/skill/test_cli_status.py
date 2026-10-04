"""One row per command across skills, and its problem-first status."""

from __future__ import annotations

from datetime import UTC, datetime

from coffer.domain.skill.cli_status import (
    CliStatus,
    LoginState,
    ProbeResult,
    SkillRequirements,
    aggregate,
    login_state,
    status_of,
)
from coffer.domain.skill.requirements import CommandRequirement

T0 = datetime(2026, 9, 30, tzinfo=UTC)


def _skill(name: str, *reqs: CommandRequirement) -> SkillRequirements:
    return SkillRequirements(skill_uid=f"uid-{name}", skill_name=name, requirements=reqs)


def test_rows_take_the_highest_minimum_and_the_first_skill_by_name() -> None:
    rows = aggregate(
        [
            _skill("zeta", CommandRequirement("gh", title="Z", min_version="2.40", login="z")),
            _skill("alpha", CommandRequirement("gh", min_version="2.20", login="gh auth login")),
            _skill("alpha2", CommandRequirement("jq")),
        ]
    )
    assert [r.command for r in rows] == ["gh", "jq"]
    gh = rows[0]
    assert gh.min_version == "2.40"
    assert gh.login == "gh auth login"  # alpha declares it first
    assert gh.title == "Z"  # only zeta gives a title
    assert [(n.skill_name, n.min_version) for n in gh.needed_by] == [
        ("alpha", "2.20"),
        ("zeta", "2.40"),
    ]


def _probe(path: str | None, version: str | None, login: LoginState | None) -> ProbeResult:
    return ProbeResult(path=path, version=version, login=login, checked_at=T0)


def test_status_order_of_checks() -> None:
    [row] = aggregate([_skill("s", CommandRequirement("gh", min_version="2.40"))])
    assert status_of(row, _probe(None, None, None)) is CliStatus.MISSING
    assert status_of(row, _probe("/b/gh", "2.30.0", LoginState.LOGGED_OUT)) is CliStatus.OUTDATED
    assert status_of(row, _probe("/b/gh", "2.41", LoginState.LOGGED_OUT)) is CliStatus.LOGGED_OUT
    assert status_of(row, _probe("/b/gh", "2.41", LoginState.LOGGED_IN)) is CliStatus.READY


def test_an_unreadable_version_is_not_outdated() -> None:
    [row] = aggregate([_skill("s", CommandRequirement("gh", min_version="2.40"))])
    assert status_of(row, _probe("/b/gh", None, LoginState.NOT_NEEDED)) is CliStatus.READY


def test_login_state() -> None:
    assert login_state(None, None) is LoginState.NOT_NEEDED
    assert login_state(("gh", "auth", "status"), True) is LoginState.LOGGED_IN
    assert login_state(("gh", "auth", "status"), False) is LoginState.LOGGED_OUT
    # A check that timed out or could not run is not logged in.
    assert login_state(("gh", "auth", "status"), None) is LoginState.LOGGED_OUT
