"""A Git source as a person types it (spec skill-manager "Add skills from a
Git repository")."""

from __future__ import annotations

import pytest

from coffer.domain.skill.git_url import (
    GitLocation,
    GitLocationError,
    display_url,
    normalise_subpath,
    parse_git_location,
)


def test_a_github_folder_address_is_the_repository_the_ref_and_the_path() -> None:
    loc = parse_git_location("https://github.com/acme/skills/tree/v1.2/skills/review/")
    assert loc == GitLocation(
        url="https://github.com/acme/skills", ref="v1.2", subpath="skills/review"
    )


def test_a_github_tree_address_without_a_path_is_the_repository_top() -> None:
    loc = parse_git_location("https://github.com/acme/skills/tree/main")
    assert loc == GitLocation(url="https://github.com/acme/skills", ref="main", subpath="")


def test_an_explicit_ref_and_path_win_over_the_github_address() -> None:
    loc = parse_git_location("https://github.com/acme/skills/tree/main/a", ref="v2", path="b/c")
    assert (loc.ref, loc.subpath) == ("v2", "b/c")


def test_scp_like_ssh_is_accepted_as_typed() -> None:
    loc = parse_git_location("git@github.com:acme/skills.git", ref="main")
    assert loc == GitLocation(url="git@github.com:acme/skills.git", ref="main", subpath="")


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/r.git",
        "http://example.com/r.git",
        "ssh://git@example.com/r.git",
        "git://example.com/r.git",
        "file:///tmp/r.git",
        "  'https://example.com/r.git'  ",
    ],
)
def test_the_allowed_transports_are_accepted(url: str) -> None:
    assert parse_git_location(url).url == url.strip().strip("'")


@pytest.mark.parametrize(
    "url",
    [
        "ext::sh -c touch% /tmp/pwned",
        "fd::17",
        "-uhelp",
        "--upload-pack=touch /tmp/x",
        "ftp://example.com/r.git",
        "not a url",
        "",
        "   ",
    ],
)
def test_a_transport_git_would_misread_is_refused(url: str) -> None:
    with pytest.raises(GitLocationError):
        parse_git_location(url)


@pytest.mark.parametrize("ref", ["-x", "--upload-pack=x", "has space", "a;b"])
def test_a_ref_that_is_an_option_or_not_a_name_is_refused(ref: str) -> None:
    with pytest.raises(GitLocationError):
        parse_git_location("https://example.com/r.git", ref=ref)


def test_a_blank_ref_is_the_default_branch() -> None:
    assert parse_git_location("https://example.com/r.git", ref="  ").ref is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ""),
        ("", ""),
        ("/skills/review/", "skills/review"),
        ("./skills//review", "skills/review"),
        ("skills\\review", "skills/review"),
    ],
)
def test_a_subpath_is_normalised(raw: str | None, expected: str) -> None:
    assert normalise_subpath(raw) == expected


@pytest.mark.parametrize("raw", ["..", "skills/../../etc", "a/..", "..\\x"])
def test_a_subpath_that_leaves_the_repository_is_refused(raw: str) -> None:
    with pytest.raises(GitLocationError):
        normalise_subpath(raw)
    with pytest.raises(GitLocationError):
        parse_git_location("https://example.com/r.git", path=raw)


def test_display_url_strips_credentials_only() -> None:
    assert display_url("https://user:tok@example.com/r.git") == "https://example.com/r.git"
    assert display_url("https://example.com/r.git") == "https://example.com/r.git"
    assert display_url("git@github.com:a/b.git") == "git@github.com:a/b.git"
