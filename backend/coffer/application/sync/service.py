"""Sync orchestration service (spec 010).

One ``run()`` is: ensure repo -> export local state -> commit -> pull/merge ->
(if clean) push -> import the merged result. A merge conflict stops the run with
status ``conflicted`` and imports nothing. Credentials that can't be decrypted on
this machine surface as ``credentials_locked`` (the master key is bootstrapped
out-of-band, never through the sync medium).
"""

from __future__ import annotations

import asyncio
import contextlib
import platform as _platform
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from coffer.application.audit_service import AuditService
from coffer.application.resource_service import ResourceService
from coffer.application.sync.config_service import SyncConfigService
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.identity import MachineIdentityService
from coffer.application.sync.importer import SyncImporter
from coffer.application.sync.ports import (
    CredentialSyncPort,
    GitPort,
    MasterKeyPort,
    WorkspacePort,
)
from coffer.domain.audit import AuditEventType
from coffer.domain.error_base import CofferError
from coffer.domain.errors import ConfigValidationError
from coffer.domain.resource import ResourceRef
from coffer.domain.sync.errors import (
    MasterKeyFileInvalid,
    SyncInProgress,
    SyncNotConfigured,
    SyncWorkspaceTooNew,
)
from coffer.domain.sync.manifest import SCHEMA_VERSION
from coffer.domain.sync.models import (
    DEFAULT_POLL_REMOTE_SECONDS,
    MACHINE_ENTRY_HEARTBEAT_SECONDS,
    MachineEntry,
    MachineIdentity,
    SyncConfig,
    SyncState,
    SyncStatus,
)
from coffer.domain.sync.portability import expand_home

_TERMINAL = {SyncStatus.CONFLICTED, SyncStatus.ERROR}

_REF_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_override_ref(kind: str, name: str) -> None:
    """Path params become workspace file paths — confine them to one segment."""
    for segment in (kind, name):
        if not _REF_SEGMENT.match(segment) or segment in {".", ".."}:
            raise ConfigValidationError(f"invalid resource ref segment: {segment!r}")


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
        identity: MachineIdentityService,
        workspace: WorkspacePort,
        coffer_version: str | None = None,
        home: str | None = None,
        resources: ResourceService | None = None,
    ) -> None:
        self._config = config
        self._git = git
        self._exporter = exporter
        self._importer = importer
        self._credentials = credentials
        self._master_key = master_key
        self._audit = audit
        self._identity = identity
        self._workspace = workspace
        self._coffer_version = coffer_version
        self._home = home
        self._resources = resources
        self._lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        """Whether a sync run currently holds the lock (any surface, not just
        the worker) — import-time mutations must not re-trigger auto-sync."""
        return self._lock.locked()

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
        poll_remote_seconds: int = DEFAULT_POLL_REMOTE_SECONDS,
    ) -> SyncConfig:
        return await self._config.update_config(
            remote=remote,
            enabled=enabled,
            auto=auto,
            interval_seconds=interval_seconds,
            branch=branch,
            actor=actor,
            poll_remote_seconds=poll_remote_seconds,
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
            try:
                return await self._run_locked(config, pull=pull, push=push)
            except Exception as e:
                # A failed run must be visible: the auto-sync worker swallows
                # exceptions, so without this the status would keep saying
                # clean while (e.g.) a too-new workspace never syncs again.
                await self._record_error(str(e))
                raise

    async def _run_locked(self, config: SyncConfig, *, pull: bool, push: bool) -> SyncState:
        assert config.remote is not None
        await asyncio.to_thread(self._git.ensure_repo, config.remote, config.branch)
        # A run must never blow through an unresolved merge: exporting over
        # conflicted files and committing would silently resolve local-wins,
        # destroying the other machine's edit. Resolve first.
        existing_conflicts = await asyncio.to_thread(self._git.conflicted_paths)
        if existing_conflicts:
            return await self._record_conflict(existing_conflicts)
        # Gate BEFORE export: a newer-schema manifest merged by an earlier run
        # must fail here, not be overwritten by this run's export (which would
        # silently disarm the gate and downgrade the medium).
        await asyncio.to_thread(self._check_workspace_version)
        identity = await self._identity.get()
        prior = await self._config.get_state()
        await self._exporter.export(
            quarantined=prior.quarantined_refs,
            machine_id=identity.machine_id,
            failed_state=prior.failed_state_paths,
        )
        await self._refresh_machine_entry(identity)
        await asyncio.to_thread(self._git.commit_all, f"coffer sync from {identity.display_name}")
        if pull:
            outcome = await asyncio.to_thread(self._git.pull, config.branch)
            if outcome.is_conflict:
                return await self._record_conflict(list(outcome.conflicted_paths))
        if push:
            await asyncio.to_thread(self._git.push, config.branch)
        return await self._finish_import(identity.machine_id)

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
            identity = await self._identity.get()
            return await self._finish_import(identity.machine_id)

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

    async def list_machines(self) -> tuple[MachineIdentity, list[MachineEntry]]:
        """Every machine known to the vault, plus which one is this machine.

        The local machine always appears (synthesized before its first sync),
        and its entry always carries the live display name — the workspace copy
        may lag a rename until the next run."""
        identity = await self._identity.get()
        entries = await asyncio.to_thread(self._workspace.read_machine_entries)
        result: list[MachineEntry] = []
        seen_local = False
        for entry in entries:
            if entry.machine_id == identity.machine_id:
                seen_local = True
                result.append(self._own_entry(identity, last_sync_at=entry.last_sync_at))
            else:
                result.append(entry)
        if not seen_local:
            result.append(self._own_entry(identity, last_sync_at=None))
        return identity, result

    async def list_overrides(self) -> list[tuple[str, str, dict[str, object]]]:
        """This machine's per-resource merge patches as (kind, name, patch)."""
        identity = await self._identity.get()
        overrides = await asyncio.to_thread(self._workspace.read_overrides, identity.machine_id)
        return sorted((k, n, patch) for (k, n), patch in overrides.items())

    async def set_override(
        self, kind: str, name: str, patch: dict[str, object], *, actor: str
    ) -> None:
        """Store a per-machine merge patch; applied at every import, stripped
        from every export. Takes effect locally on the next sync run."""
        _validate_override_ref(kind, name)
        identity = await self._identity.get()
        async with self._lock:  # never interleave with a run's import phase
            await asyncio.to_thread(
                self._workspace.write_override, identity.machine_id, kind, name, patch
            )
        await self._audit.record(
            AuditEventType.SYNC_OVERRIDE_SET.value,
            actor=actor,
            details={"resource": f"{kind}:{name}", "keys": sorted(patch)},
        )

    async def unset_override(self, kind: str, name: str, *, actor: str) -> None:
        _validate_override_ref(kind, name)
        identity = await self._identity.get()
        # Under the run lock: interleaving with an in-flight import would let
        # the import re-apply the just-deleted patch onto the live row, and
        # the next export would publish the specialization as shared state.
        async with self._lock:
            await asyncio.to_thread(
                self._workspace.remove_override, identity.machine_id, kind, name
            )
            # Restore the local resource to the shared view NOW: export runs
            # before import, so a live row still carrying the patched values
            # would leak this machine's specialization on the next run.
            shared = {
                (d.kind, d.name): d
                for d in await asyncio.to_thread(self._workspace.read_resource_docs)
            }
            doc = shared.get((kind, name))
            if doc is not None and self._resources is not None:
                config = expand_home(doc.config, self._home) if self._home else dict(doc.config)
                with contextlib.suppress(CofferError):  # may not exist locally yet
                    await self._resources.update_config(
                        ResourceRef(kind, name), config, actor, allow_lifecycle_kind=True
                    )
        await self._audit.record(
            AuditEventType.SYNC_OVERRIDE_UNSET.value,
            actor=actor,
            details={"resource": f"{kind}:{name}"},
        )

    async def rename_machine(self, display_name: str, *, actor: str) -> MachineIdentity:
        """Rename this machine; the change reaches other machines on the next run."""
        return await self._identity.rename(display_name, actor=actor)

    # --- internals ---------------------------------------------------------

    def _own_entry(
        self, identity: MachineIdentity, *, last_sync_at: datetime | None
    ) -> MachineEntry:
        return MachineEntry(
            machine_id=identity.machine_id,
            display_name=identity.display_name,
            platform=_platform.system().lower(),
            os_version=_platform.release(),
            coffer_version=self._coffer_version,
            last_sync_at=last_sync_at,
        )

    async def _refresh_machine_entry(self, identity: MachineIdentity) -> None:
        """Rewrite this machine's registry entry only when the run has other
        changes, the name changed, or the entry is stale (the 24 h heartbeat) —
        an idle machine must not generate registry-only commit chains."""

        def _refresh() -> None:
            own = next(
                (
                    e
                    for e in self._workspace.read_machine_entries()
                    if e.machine_id == identity.machine_id
                ),
                None,
            )
            now = datetime.now(tz=UTC)
            stale = own is None or own.display_name != identity.display_name
            if not stale and own is not None:
                ts = own.last_sync_at
                if ts is not None and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                stale = ts is None or (now - ts).total_seconds() > MACHINE_ENTRY_HEARTBEAT_SECONDS
            if stale or self._git.has_changes():
                self._workspace.write_machine_entry(self._own_entry(identity, last_sync_at=now))

        await asyncio.to_thread(_refresh)

    def _check_workspace_version(self) -> None:
        manifest = self._workspace.read_manifest()
        if manifest is not None and manifest.schema_version > SCHEMA_VERSION:
            raise SyncWorkspaceTooNew(manifest.schema_version, SCHEMA_VERSION)

    async def _record_error(self, message: str) -> None:
        prior = await self._config.get_state()
        await self._config.set_state(
            SyncState(
                status=SyncStatus.ERROR,
                last_sync_at=prior.last_sync_at,
                last_error=message,
                locked_refs=prior.locked_refs,
                quarantined_refs=prior.quarantined_refs,
                failed_state_paths=prior.failed_state_paths,
            )
        )

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

    async def _finish_import(self, machine_id: str | None = None) -> SyncState:
        result = await self._importer.import_(machine_id)
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
            quarantined_refs=sorted(set(result.quarantined_refs)),
            failed_state_paths=sorted(set(result.failed_state_paths)),
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
                "quarantined": len(result.quarantined_refs),
            },
        )
        return saved
