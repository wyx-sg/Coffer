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
    quarantined_refs: list[str] = field(default_factory=list)
    updated_at: datetime | None = None


#: How long an exported tombstone (and its ledger row) lives before pruning.
TOMBSTONE_TTL_SECONDS = 90 * 24 * 3600


@dataclass(frozen=True)
class Tombstone:
    """The explicit record of a config-resource deletion (spec 010).

    Import deletes a local resource only when its tombstone is present;
    absence from the workspace alone never deletes."""

    kind: str
    name: str
    deleted_at: datetime
    by: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {"deleted_at": self.deleted_at.isoformat(), "by": self.by}


#: How stale this machine's registry entry may get before a run rewrites it
#: even without other changes (the heartbeat; see spec 010 "Machine identity").
MACHINE_ENTRY_HEARTBEAT_SECONDS = 24 * 3600


@dataclass(frozen=True)
class MachineIdentity:
    """This installation's stable identity (ADR-043). Machine-local, never synced."""

    machine_id: str
    display_name: str


@dataclass(frozen=True)
class MachineEntry:
    """One machine's registry entry in the workspace ``machines/`` area.

    Written only by its owning machine, so entries never merge-conflict."""

    machine_id: str
    display_name: str
    platform: str | None = None
    os_version: str | None = None
    coffer_version: str | None = None
    last_sync_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "machine_id": self.machine_id,
            "display_name": self.display_name,
            "platform": self.platform,
            "os_version": self.os_version,
            "coffer_version": self.coffer_version,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> MachineEntry:
        raw_ts = data.get("last_sync_at")
        return cls(
            machine_id=str(data["machine_id"]),
            display_name=str(data.get("display_name") or data["machine_id"]),
            platform=str(data["platform"]) if data.get("platform") else None,
            os_version=str(data["os_version"]) if data.get("os_version") else None,
            coffer_version=str(data["coffer_version"]) if data.get("coffer_version") else None,
            last_sync_at=datetime.fromisoformat(str(raw_ts)) if raw_ts else None,
        )
