"""The backup remote: one user-owned git repository exports are pushed to.

Spec vault-export-import ``## Backup``; constitution 0.5.0 Principle I
exception. Pure domain — no filesystem, no git, no database. Everything here
is about what a valid remote *is* and what one run of a backup *reports*; how
either is carried out belongs to the application layer.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum

from coffer.domain.sync.errors import BackupRemoteInvalid

DEFAULT_BRANCH = "main"
DEFAULT_INTERVAL_SECONDS = 3600
DEFAULT_WORKTREE = "~/.coffer/sync"


class BackupRunStatus(StrEnum):
    """What one backup run actually achieved.

    ``NO_CHANGE`` is a success, not a skip: a deterministic export that matches
    the last one means the vault did not change, so the history records changes
    rather than ticks. ``PUSH_FAILED`` means the commit exists locally and is
    waiting for a later run to push it — it is never rolled back, because the
    local history is itself the first layer of recovery.
    """

    OK = "ok"
    NO_CHANGE = "no_change"
    PUSH_FAILED = "push_failed"
    EXPORT_FAILED = "export_failed"


@dataclasses.dataclass(frozen=True, slots=True)
class BackupRemote:
    """Where backups go, and how often.

    ``credential_ref`` names a secret in the credential store; the secret
    itself never lives on this object, so a remote can be logged, serialized
    into an API response or rendered in the UI without redaction.

    ``include_credentials`` is fixed here rather than per run: it is the same
    deliberate opt-in the ``--with-credentials`` flag expresses for a manual
    export, and a backup that silently changed what it carried between runs
    would be worse than either answer.
    """

    url: str
    branch: str = DEFAULT_BRANCH
    credential_ref: str | None = None
    include_credentials: bool = False
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS
    enabled: bool = True
    worktree_path: str = DEFAULT_WORKTREE

    def __post_init__(self) -> None:
        url = self.url.strip()
        if not url:
            raise BackupRemoteInvalid("url must not be empty")
        branch = self.branch.strip()
        if not branch:
            raise BackupRemoteInvalid("branch must not be empty")
        if self.interval_seconds <= 0:
            raise BackupRemoteInvalid("interval must be a positive number of seconds")
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "branch", branch)


@dataclasses.dataclass(frozen=True, slots=True)
class BackupRun:
    """The outcome of one backup run, as stored and as reported."""

    status: BackupRunStatus
    commit: str | None = None
    error: str | None = None
    ran_at: datetime | None = None


def redact(text: str, secret: str | None) -> str:
    """Replace every occurrence of ``secret`` in ``text`` with ``***``.

    Git reports an authentication failure with the URL it tried, and a token
    embedded in that URL would otherwise reach an audit row, a status field or
    a terminal. Every git error passes through here before it is stored or
    shown.
    """
    if not secret:
        return text
    return text.replace(secret, "***")
