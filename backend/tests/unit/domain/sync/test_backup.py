"""Domain rules for the sync remote (spec vault-sync "Allow at most one user-owned sync remote")."""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from coffer.domain.sync.backup import (
    DEFAULT_BRANCH,
    DEFAULT_INTERVAL_SECONDS,
    BackupRemote,
    redact,
    validate_branch,
    validate_url,
    worktree_conflict,
)
from coffer.domain.sync.errors import BackupRemoteInvalid


def test_defaults_are_the_spec_defaults() -> None:
    remote = BackupRemote(url="https://example.invalid/vault.git")
    assert remote.branch == DEFAULT_BRANCH == "main"
    assert remote.interval_seconds == DEFAULT_INTERVAL_SECONDS == 3600
    assert remote.include_credentials is False
    assert remote.enabled is True
    assert remote.worktree_path == "~/.coffer/sync"


@pytest.mark.parametrize(
    ("kwargs", "needle"),
    [
        ({"url": "   "}, "url"),
        ({"url": "https://example.invalid/v.git", "interval_seconds": 0}, "interval"),
        ({"url": "https://example.invalid/v.git", "interval_seconds": -1}, "interval"),
        ({"url": "https://example.invalid/v.git", "branch": ""}, "branch"),
        ({"url": "https://example.invalid/v.git", "worktree_path": "  "}, "worktree"),
    ],
)
def test_invalid_configuration_is_refused(kwargs: dict[str, object], needle: str) -> None:
    with pytest.raises(BackupRemoteInvalid) as excinfo:
        BackupRemote(**kwargs)  # type: ignore[arg-type]
    assert needle in str(excinfo.value).lower()


def test_url_and_branch_are_stripped() -> None:
    remote = BackupRemote(url="  https://example.invalid/v.git  ", branch="  main  ")
    assert remote.url == "https://example.invalid/v.git"
    assert remote.branch == "main"


# --- option injection --------------------------------------------------------
#
# The URL and the branch end up in ``git``'s argv. ``--receive-pack=<cmd>`` is
# a command git runs on push, so a value git would read as an option is refused
# on the value itself, before any adapter sees it.


@pytest.mark.parametrize(
    "branch",
    [
        "-x",
        "--receive-pack=touch /tmp/pwned",
        "--upload-pack=x",
        "a..b",
        "a b",
        "a\tb",
        "a.lock",
        "a.lock/b",
        ".hidden",
        "a/.hidden",
        "a~1",
        "a^",
        "a:b",
        "a?",
        "a*",
        "a[",
        "a\\b",
        "a@{b",
        "a/",
        "/a",
        "a//b",
        "a.",
        "HEAD",
        "ctl\x01",
        "del\x7f",
    ],
)
@pytest.mark.acceptance(
    spec="vault-sync", scenario="a remote URL or branch that git would read as an option is refused"
)
def test_a_branch_git_would_refuse_or_read_as_an_option_is_refused(branch: str) -> None:
    with pytest.raises(BackupRemoteInvalid):
        validate_branch(branch)
    with pytest.raises(BackupRemoteInvalid):
        BackupRemote(url="https://example.invalid/v.git", branch=branch)


@pytest.mark.parametrize("branch", ["main", "feat/x", "release-1.2", "a.b", "中文", "x-y", "@"])
def test_an_ordinary_branch_name_is_accepted_unchanged(branch: str) -> None:
    assert validate_branch(branch) == branch
    assert BackupRemote(url="https://example.invalid/v.git", branch=branch).branch == branch


@pytest.mark.parametrize("url", ["-x", "--receive-pack=x", "--upload-pack=x", " -f"])
@pytest.mark.acceptance(
    spec="vault-sync", scenario="a remote URL or branch that git would read as an option is refused"
)
def test_a_url_git_would_read_as_an_option_is_refused(url: str) -> None:
    with pytest.raises(BackupRemoteInvalid) as excinfo:
        validate_url(url)
    assert "'-'" in str(excinfo.value)
    with pytest.raises(BackupRemoteInvalid):
        BackupRemote(url=url)


@pytest.mark.parametrize(
    "url",
    ["https://example.invalid/v.git", "git@github.com:me/vault.git", "file:///tmp/v.git", "/tmp/v"],
)
def test_ordinary_remote_urls_are_accepted(url: str) -> None:
    assert BackupRemote(url=url).url == url


# --- the working tree's place --------------------------------------------------

_COFFER = PurePosixPath("/home/u/.coffer")
_ROOTS = [_COFFER / "knowledge", _COFFER / "skills", _COFFER / "memory"]
_DEFAULT = _COFFER / "sync"


def _conflict(path: str) -> str | None:
    return worktree_conflict(
        PurePosixPath(path),
        mirrored_roots=_ROOTS,
        coffer_dir=_COFFER,
        default_worktree=_DEFAULT,
    )


@pytest.mark.parametrize(
    "path",
    ["/home/u/.coffer/sync", "/home/u/.coffer/sync/nested", "/home/u/vault-mirror", "/srv/coffer"],
)
def test_a_working_tree_beside_the_vault_is_allowed(path: str) -> None:
    assert _conflict(path) is None


@pytest.mark.parametrize(
    ("path", "needle"),
    [
        ("/home/u/.coffer/knowledge", "overlaps"),
        ("/home/u/.coffer/knowledge/notes", "overlaps"),
        ("/home/u/.coffer/skills", "overlaps"),
        ("/home/u/.coffer/memory/projects", "overlaps"),
        ("/home/u/.coffer", "Coffer's own directory"),
        ("/home/u", "Coffer's own directory"),
        ("/", "Coffer's own directory"),
        ("/home/u/.coffer/other", "only /home/u/.coffer/sync is allowed"),
    ],
)
def test_a_working_tree_that_would_swallow_the_vault_is_refused(path: str, needle: str) -> None:
    reason = _conflict(path)
    assert reason is not None
    assert needle in reason


# --- redaction ---------------------------------------------------------------


def test_redact_removes_every_occurrence() -> None:
    text = "fatal: could not read Password for 'https://tok123@host': tok123"
    assert redact(text, "tok123") == "fatal: could not read Password for 'https://***@host': ***"


def test_redact_is_a_noop_without_a_secret() -> None:
    assert redact("plain text", None) == "plain text"
    assert redact("plain text", "") == "plain text"
