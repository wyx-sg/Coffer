"""The compare link of a skill's update (spec skill-manager "Hand a Git-imported
skill's update to an agent")."""

from __future__ import annotations

import pytest

from coffer.domain.skill.compare_url import compare_url


@pytest.mark.acceptance(
    spec="skill-manager", scenario="the compare link is built for GitHub and GitLab only"
)
def test_the_compare_link_is_built_for_github_and_gitlab_only() -> None:
    github = "https://github.com/acme/skills/compare/a1...c3"
    assert compare_url("https://github.com/acme/skills.git", "a1", "c3") == github
    assert compare_url("git@github.com:acme/skills.git", "a1", "c3") == github
    assert (
        compare_url("ssh://git@gitlab.com/group/sub/skills.git", "a1", "c3")
        == "https://gitlab.com/group/sub/skills/-/compare/a1...c3"
    )
    assert (
        compare_url("https://gitlab.example.com/group/skills", "a1", "c3")
        == "https://gitlab.example.com/group/skills/-/compare/a1...c3"
    )
    assert compare_url("https://git.example.com/acme/skills.git", "a1", "c3") is None


@pytest.mark.parametrize(
    "url",
    [
        "https://user:token@github.com/acme/skills.git",
        "https://token@github.com/acme/skills",
        "ssh://git:pw@github.com/acme/skills.git",
    ],
)
def test_a_link_never_carries_a_credential(url: str) -> None:
    link = compare_url(url, "a1", "c3")
    assert link == "https://github.com/acme/skills/compare/a1...c3"


@pytest.mark.parametrize(
    "url",
    ["http://github.com/acme/skills", "git://github.com/acme/skills", "file:///tmp/repo.git"],
)
def test_other_transports_have_no_link(url: str) -> None:
    assert compare_url(url, "a1", "c3") is None
