"""Sync configuration + state service (spec 010).

Reads/writes the singleton sync_config and sync_state rows. No secrets — git
remote auth is the user's ambient git configuration.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from coffer.application.audit_service import AuditService
from coffer.domain.audit import AuditEventType
from coffer.domain.errors import ConfigValidationError
from coffer.domain.sync.models import (
    DEFAULT_BRANCH,
    DEFAULT_INTERVAL_SECONDS,
    DEFAULT_POLL_REMOTE_SECONDS,
    MIN_INTERVAL_SECONDS,
    MIN_POLL_REMOTE_SECONDS,
    SyncConfig,
    SyncState,
    SyncStatus,
)


class SyncConfigRepo(Protocol):
    async def get(self) -> SyncConfig | None: ...
    async def set(
        self,
        *,
        remote: str | None,
        enabled: bool,
        auto: bool,
        interval_seconds: int,
        branch: str,
        poll_remote_seconds: int = DEFAULT_POLL_REMOTE_SECONDS,
    ) -> SyncConfig: ...


class SyncStateRepo(Protocol):
    async def get(self) -> SyncState | None: ...
    async def set(self, state: SyncState) -> SyncState: ...


def _default_config() -> SyncConfig:
    return SyncConfig(
        remote=None,
        enabled=False,
        auto=False,
        interval_seconds=DEFAULT_INTERVAL_SECONDS,
        branch=DEFAULT_BRANCH,
        updated_at=datetime.now(tz=UTC),
        poll_remote_seconds=DEFAULT_POLL_REMOTE_SECONDS,
    )


class SyncConfigService:
    """Reads/writes the singleton sync config and state rows."""

    def __init__(
        self, config_repo: SyncConfigRepo, state_repo: SyncStateRepo, audit: AuditService
    ) -> None:
        self._config = config_repo
        self._state = state_repo
        self._audit = audit

    async def get_config(self) -> SyncConfig:
        return await self._config.get() or _default_config()

    async def update_config(
        self,
        *,
        remote: str | None,
        enabled: bool,
        auto: bool,
        interval_seconds: int,
        branch: str,
        actor: str,
        poll_remote_seconds: int = DEFAULT_POLL_REMOTE_SECONDS,
    ) -> SyncConfig:
        if interval_seconds < MIN_INTERVAL_SECONDS:
            raise ConfigValidationError(
                f"interval_seconds must be >= {MIN_INTERVAL_SECONDS}, got {interval_seconds}"
            )
        if poll_remote_seconds < MIN_POLL_REMOTE_SECONDS:
            raise ConfigValidationError(
                f"poll_remote_seconds must be >= {MIN_POLL_REMOTE_SECONDS}, "
                f"got {poll_remote_seconds}"
            )
        if enabled and not remote:
            raise ConfigValidationError("a remote is required to enable sync")
        if not branch:
            raise ConfigValidationError("branch must not be empty")
        saved = await self._config.set(
            remote=remote or None,
            enabled=enabled,
            auto=auto,
            interval_seconds=interval_seconds,
            branch=branch,
            poll_remote_seconds=poll_remote_seconds,
        )
        await self._audit.record(
            AuditEventType.SYNC_CONFIG_UPDATED.value,
            actor=actor,
            details={
                "remote_set": bool(saved.remote),
                "enabled": saved.enabled,
                "auto": saved.auto,
                "interval_seconds": saved.interval_seconds,
                "poll_remote_seconds": saved.poll_remote_seconds,
                "branch": saved.branch,
            },
        )
        return saved

    async def get_state(self) -> SyncState:
        existing = await self._state.get()
        if existing is not None:
            return existing
        # No run yet: status reflects whether a remote is configured.
        config = await self.get_config()
        status = SyncStatus.CLEAN if config.is_operational() else SyncStatus.UNCONFIGURED
        return SyncState(status=status, last_sync_at=None, last_error=None)

    async def set_state(self, state: SyncState) -> SyncState:
        return await self._state.set(state)
