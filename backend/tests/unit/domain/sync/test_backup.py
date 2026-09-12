"""Domain rules for the backup remote (spec vault-export-import ``## Backup``)."""

from __future__ import annotations

import pytest

from coffer.domain.sync.backup import (
    DEFAULT_BRANCH,
    DEFAULT_INTERVAL_SECONDS,
    BackupRemote,
    BackupRun,
    BackupRunStatus,
    redact,
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


def test_redact_removes_every_occurrence() -> None:
    text = "fatal: could not read Password for 'https://tok123@host': tok123"
    assert redact(text, "tok123") == "fatal: could not read Password for 'https://***@host': ***"


def test_redact_is_a_noop_without_a_secret() -> None:
    assert redact("plain text", None) == "plain text"
    assert redact("plain text", "") == "plain text"


def test_run_carries_its_outcome() -> None:
    run = BackupRun(status=BackupRunStatus.PUSH_FAILED, commit="abc1234", error="offline")
    assert run.status is BackupRunStatus.PUSH_FAILED
    assert run.commit == "abc1234"
    assert run.error == "offline"


def test_no_change_is_a_distinct_status_from_ok() -> None:
    # A tick that found nothing to do must be distinguishable from one that
    # pushed, or "last run: ok" stops meaning anything.
    assert BackupRunStatus.NO_CHANGE is not BackupRunStatus.OK
    assert str(BackupRunStatus.NO_CHANGE) == "no_change"
