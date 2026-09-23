"""What a repository's identity is, and what a partition is named (see
"Identify a partition by its repository").

Pure domain: ``domain/memory/repository.py`` decides which key a repository
answers to once its root and remote are known, and ``domain/memory/partition.py``
turns a repository name into a readable slug. Walking a real ``.git`` to find
those two things is infrastructure's, and is exercised against real
``git init`` / ``git worktree add`` fixtures in
``tests/integration/memory/test_partitions_are_repositories.py``.

The property under test is one sentence: **two clones of one upstream are one
repository**, whatever spelling of the remote each of them was configured
with. Comparing remotes literally is what would file a worktree, a second
clone and the main checkout into three partitions.
"""

from __future__ import annotations

import pytest

from coffer.domain.memory.partition import GLOBAL_PARTITION, disambiguate, partition_slug
from coffer.domain.memory.repository import (
    SCHEME_PATH,
    SCHEME_REMOTE,
    normalise_remote,
    repository_key,
    repository_name,
)


@pytest.mark.parametrize(
    "url",
    [
        "git@github.com:owner/repo.git",
        "https://github.com/owner/repo",
        "https://github.com/owner/repo.git",
        "https://github.com/owner/repo/",
        "ssh://git@github.com:22/owner/repo.git",
        "https://user@GitHub.com/owner/repo",
    ],
)
def test_every_spelling_of_one_upstream_normalises_to_one_key(url: str) -> None:
    assert normalise_remote(url) == "github.com/owner/repo"


def test_the_paths_case_is_kept_because_two_forges_distinguish_it() -> None:
    """Folding the host is right; folding the path would file two real
    repositories together, which is the worse error."""
    assert normalise_remote("git@github.com:owner/Repo.git") == "github.com/owner/Repo"


@pytest.mark.parametrize("url", ["", "   ", "not a url", "/plain/path", "owner/repo"])
def test_something_that_is_not_a_remote_normalises_to_nothing(url: str) -> None:
    assert normalise_remote(url) == ""


def test_two_clones_of_one_upstream_answer_to_one_key() -> None:
    first = repository_key(remote_url="git@github.com:owner/repo.git", root_path="/home/dev/repo")
    second = repository_key(
        remote_url="https://github.com/owner/repo", root_path="/elsewhere/repo-two"
    )
    assert first == second == f"{SCHEME_REMOTE}:github.com/owner/repo"


def test_a_repository_with_no_remote_falls_back_to_its_own_path() -> None:
    assert repository_key(remote_url="", root_path="/home/dev/local-only/") == (
        f"{SCHEME_PATH}:/home/dev/local-only"
    )


def test_a_path_key_can_never_collide_with_a_remote_key() -> None:
    """The prefixes are what keep the two namespaces apart."""
    path_key = repository_key(remote_url="", root_path="/github.com/owner/repo")
    remote = repository_key(remote_url="https://github.com/owner/repo", root_path="/x")
    assert path_key != remote


def test_neither_a_remote_nor_a_path_is_no_repository_at_all() -> None:
    assert repository_key(remote_url="", root_path="") == ""


def test_the_name_comes_from_the_remote_so_two_clones_agree_on_it() -> None:
    assert (
        repository_name(remote_url="git@github.com:owner/coffer.git", root_path="/tmp/checkout-b")
        == "coffer"
    )


def test_without_a_remote_the_name_is_the_directorys_own() -> None:
    assert repository_name(remote_url="", root_path="/home/dev/coffer/") == "coffer"
    assert repository_name(remote_url="", root_path="") == ""


def test_a_partition_slug_is_the_directory_name_readably() -> None:
    assert partition_slug("/home/dev/Coffer") == "coffer"
    assert partition_slug("/home/dev/my@@project") == "my-project"


def test_a_partition_slug_never_degrades_to_an_opaque_id() -> None:
    """The failure that got the previous per-project store removed: nobody
    could tell which project a ``project-<ULID>`` store belonged to."""
    assert partition_slug("") == GLOBAL_PARTITION
    assert partition_slug("/") == GLOBAL_PARTITION


def test_two_projects_with_one_name_are_told_apart_by_their_parent() -> None:
    assert disambiguate("/home/dev/work/api", frozenset({"api"})) == "work-api"
    assert disambiguate("/home/dev/personal/api", frozenset({"api", "work-api"})) == (
        "personal-api"
    )


def test_a_numeric_suffix_is_the_last_resort_not_the_first() -> None:
    taken = frozenset({"api", "work-api", "dev-work-api", "home-dev-work-api"})
    assert disambiguate("/home/dev/work/api", taken) == "home-dev-work-api-2"


def test_a_rootless_path_disambiguates_to_global() -> None:
    assert disambiguate("", frozenset()) == GLOBAL_PARTITION
