"""Sync configuration and run-state value objects (spec 010)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

#: The fixed primary key shared by the singleton sync_config / sync_state rows.
SINGLETON_ID = 1

#: Default auto-sync pull/push interval (seconds).
DEFAULT_INTERVAL_SECONDS = 300

#: Minimum auto-sync interval; below this the worker would thrash the remote.
MIN_INTERVAL_SECONDS = 30

#: Default git branch synced on.
DEFAULT_BRANCH = "main"


class SyncStatus(StrEnum):
    """The state of the last sync run."""

    UNCONFIGURED = "unconfigured"
    CLEAN = "clean"
    SYNCING = "syncing"
    CONFLICTED = "conflicted"
    ERROR = "error"
    CREDENTIALS_LOCKED = "credentials_locked"


@dataclass
class SyncConfig:
    """User-controlled sync configuration. No secrets — git auth is ambient."""

    remote: str | None
    enabled: bool
    auto: bool
    interval_seconds: int
    branch: str
    updated_at: datetime

    def is_operational(self) -> bool:
        """Whether a sync run can actually run (a remote is set and enabled)."""
        return self.enabled and bool(self.remote)


@dataclass
class SyncState:
    """Outcome of the most recent sync run."""

    status: SyncStatus
    last_sync_at: datetime | None
    last_error: str | None
    conflict_paths: list[str] = field(default_factory=list)
    locked_refs: list[str] = field(default_factory=list)
    updated_at: datetime | None = None
