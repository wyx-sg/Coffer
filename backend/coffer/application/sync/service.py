"""Sync orchestration service (spec 010).

One ``run()`` is: ensure repo -> export local state -> commit -> pull/merge ->
(if clean) push -> import the merged result. A merge conflict stops the run with
status ``conflicted`` and imports nothing. Credentials that can't be decrypted on
this machine surface as ``credentials_locked`` (the master key is bootstrapped
out-of-band, never through the sync medium).
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from coffer.application.audit_service import AuditService
from coffer.application.sync.config_service import SyncConfigService
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.importer import SyncImporter
from coffer.application.sync.ports import CredentialSyncPort, GitPort, MasterKeyPort
from coffer.domain.audit import AuditEventType
from coffer.domain.sync.errors import MasterKeyFileInvalid, SyncInProgress, SyncNotConfigured
from coffer.domain.sync.models import SyncConfig, SyncState, SyncStatus

_TERMINAL = {SyncStatus.CONFLICTED, SyncStatus.ERROR}


class SyncService:
    def __init__(
        self,
        *,
        config: SyncConfigService,
        git: GitPort,
        exporter: SyncExporter,
        importer: SyncImporter,
        credentials: CredentialSyncPort,
        master_key: MasterKeyPort,
        audit: AuditService,
        machine_id: str,
    ) -> None:
        self._config = config
        self._git = git
        self._exporter = exporter
        self._importer = importer
        self._credentials = credentials
        self._master_key = master_key
        self._audit = audit
        self._machine_id = machine_id
        self._lock = asyncio.Lock()

    async def get_config(self) -> SyncConfig:
        return await self._config.get_config()

    async def update_config(
        self,
        *,
        remote: str | None,
        enabled: bool,
        auto: bool,
        interval_seconds: int,
        branch: str,
        actor: str,
    ) -> SyncConfig:
        return await self._config.update_config(
            remote=remote,
            enabled=enabled,
            auto=auto,
            interval_seconds=interval_seconds,
            branch=branch,
            actor=actor,
        )

    async def status(self) -> SyncState:
        config = await self._config.get_config()
        if not config.is_operational():
            return SyncState(status=SyncStatus.UNCONFIGURED, last_sync_at=None, last_error=None)
        state = await self._config.get_state()
        if state.status not in _TERMINAL:
            locked = await asyncio.to_thread(self._credentials.locked_refs)
            state.locked_refs = locked
            state.status = SyncStatus.CREDENTIALS_LOCKED if locked else SyncStatus.CLEAN
        return state

    async def run(self, *, pull: bool = True, push: bool = True) -> SyncState:
        config = await self._config.get_config()
        if not config.is_operational():
            raise SyncNotConfigured()
        if self._lock.locked():
            raise SyncInProgress()
        async with self._lock:
            assert config.remote is not None
            await asyncio.to_thread(self._git.ensure_repo, config.remote, config.branch)
            await self._exporter.export()
            await asyncio.to_thread(
                self._git.commit_all, f"coffer sync from {self._machine_id}"
            )
            if pull:
                outcome = await asyncio.to_thread(self._git.pull, config.branch)
                if outcome.is_conflict:
                    return await self._record_conflict(list(outcome.conflicted_paths))
            if push:
                await asyncio.to_thread(self._git.push, config.branch)
            return await self._finish_import()

    async def resolve(self, strategy: str, paths: Sequence[str]) -> SyncState:
        config = await self._config.get_config()
        if not config.is_operational():
            raise SyncNotConfigured()
        async with self._lock:
            await asyncio.to_thread(self._git.resolve, strategy, list(paths))
            if await asyncio.to_thread(self._git.has_conflicts):
                remaining = await asyncio.to_thread(self._git.conflicted_paths)
                return await self._record_conflict(remaining)
            await asyncio.to_thread(self._git.push, config.branch)
            await self._audit.record(AuditEventType.SYNC_RESOLVED.value, actor="sync")
            return await self._finish_import()

    async def export_key(self, path: str) -> str:
        key = self._master_key.export_key()
        if key is None:
            raise MasterKeyFileInvalid(path, "no master key on this machine to export")
        target = Path(path).expanduser()
        await asyncio.to_thread(target.write_bytes, key)
        await asyncio.to_thread(target.chmod, 0o600)
        await self._audit.record(AuditEventType.MASTER_KEY_EXPORTED.value, actor="sync")
        return str(target)

    async def import_key(self, path: str) -> SyncState:
        source = Path(path).expanduser()
        if not source.exists():
            raise MasterKeyFileInvalid(path, "file does not exist")
        raw = await asyncio.to_thread(source.read_bytes)
        try:
            await asyncio.to_thread(self._master_key.install_key, raw)
        except ValueError as e:
            raise MasterKeyFileInvalid(path, "not a valid Fernet key") from e
        await self._audit.record(AuditEventType.MASTER_KEY_IMPORTED.value, actor="sync")
        return await self.status()

    # --- internals ---------------------------------------------------------

    async def _record_conflict(self, paths: list[str]) -> SyncState:
        state = SyncState(
            status=SyncStatus.CONFLICTED,
            last_sync_at=None,
            last_error=None,
            conflict_paths=paths,
        )
        saved = await self._config.set_state(state)
        await self._audit.record(
            AuditEventType.SYNC_CONFLICTED.value, actor="sync", details={"paths": len(paths)}
        )
        return saved

    async def _finish_import(self) -> SyncState:
        result = await self._importer.import_()
        if result.errors:
            status = SyncStatus.ERROR
            last_error = "; ".join(result.errors[:5])
        elif result.locked_refs:
            status = SyncStatus.CREDENTIALS_LOCKED
            last_error = None
        else:
            status = SyncStatus.CLEAN
            last_error = None
        state = SyncState(
            status=status,
            last_sync_at=datetime.now(tz=UTC),
            last_error=last_error,
            locked_refs=result.locked_refs,
        )
        saved = await self._config.set_state(state)
        await self._audit.record(
            AuditEventType.SYNC_COMPLETED.value,
            actor="sync",
            details={
                "applied": result.applied,
                "deleted": result.deleted,
                "errors": len(result.errors),
                "locked": len(result.locked_refs),
            },
        )
        return saved
