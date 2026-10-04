"""Which git the vault runs on (spec daemon "Wait in a setup state when git is
missing or too old"): the daemon's ``PATH`` first, then the login shell's.

The finder is injected, so no test here runs git or a shell.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import pytest

from coffer.domain.git_handoff import git_setup_details, git_setup_message
from coffer.infrastructure.vault.git_requirement import (
    FoundGit,
    GitCheck,
    check_git,
    parse_version,
    use_git_dir,
)

_OWN = "/usr/bin:/bin"
_LOGIN = "/opt/homebrew/bin:/usr/bin:/bin"


def _finder(by_path: dict[str, FoundGit | None]) -> Callable[[str], FoundGit | None]:
    return lambda search_path: by_path.get(search_path)


def _check(own: FoundGit | None, login: FoundGit | None) -> GitCheck:
    return check_git(
        daemon_path=_OWN, login_path=lambda: _LOGIN, finder=_finder({_OWN: own, _LOGIN: login})
    )


def test_the_daemons_own_git_wins_when_it_is_new_enough() -> None:
    own = FoundGit("/usr/bin/git", (2, 50))
    check = _check(own, FoundGit("/opt/homebrew/bin/git", (2, 51)))
    assert check.ok and check.usable == own and not check.from_login_path


@pytest.mark.acceptance(spec="daemon", scenario="a git only on the login shell's PATH is used")
def test_a_git_only_on_the_login_path_is_used_and_put_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    login = FoundGit("/opt/homebrew/bin/git", (2, 45))
    check = _check(FoundGit("/usr/bin/git", (2, 30)), login)
    assert check.ok and check.usable == login and check.from_login_path

    monkeypatch.setenv("PATH", os.pathsep.join(["/usr/bin", "/opt/homebrew/bin", "/bin"]))
    use_git_dir(check)
    assert os.environ["PATH"].split(os.pathsep) == ["/opt/homebrew/bin", "/usr/bin", "/bin"]


def test_the_daemons_own_git_leaves_path_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", _OWN)
    use_git_dir(_check(FoundGit("/usr/bin/git", (2, 40)), None))
    assert os.environ["PATH"] == _OWN


def test_no_git_anywhere_is_missing() -> None:
    check = _check(None, None)
    assert not check.ok and check.found is None and check.found_version is None


def test_the_newest_old_git_is_the_one_reported() -> None:
    check = _check(FoundGit("/usr/bin/git", (2, 30)), FoundGit("/opt/homebrew/bin/git", (2, 39)))
    assert not check.ok and check.found_version == "2.39"


@pytest.mark.parametrize(
    ("output", "version"),
    [
        ("git version 2.50.1 (Apple Git-155)\n", (2, 50)),
        ("git version 2.43.0.windows.1", (2, 43)),
        ("git version 2.9", (2, 9)),
        ("not git", None),
        ("", None),
    ],
)
def test_parse_version(output: str, version: tuple[int, int] | None) -> None:
    assert parse_version(output) == version


def test_the_setup_words_say_what_is_wrong_and_why() -> None:
    missing = git_setup_message(found=None, needed="2.40")
    assert "git isn't installed on this machine" in missing
    assert "The vault keeps its history and syncs with git." in missing
    assert "Install git" in missing
    old = git_setup_message(found="2.30", needed="2.40")
    assert "Coffer needs git 2.40 or later, and the git on this machine is 2.30." in old
    assert "Update git" in old

    details = git_setup_details("macOS arm64", found="2.30", needed="2.40")
    assert details["reason"] == "git_too_old"
    assert (details["found"], details["needed"]) == ("2.30", "2.40")
    prompt = details["handoff"]["prompt"]  # type: ignore[index]
    assert "Please update git on this machine to version 2.40 or later." in prompt
    assert "brew" not in prompt
    assert git_setup_details("macOS arm64", found=None, needed="2.40")["reason"] == "git_missing"
