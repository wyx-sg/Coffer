"""Vault export/import service (spec 010, ADR-016).

Two operations over a directory the user names, plus the out-of-band master-key
bootstrap. No remote, no background replication, no state machine: each call
does its work and reports a summary.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from pathlib import Path

from coffer.application.audit_service import AuditService
from coffer.application.sync.exporter import SyncExporter
from coffer.application.sync.importer import SyncImporter
from coffer.application.sync.ports import BundlePort, CredentialSyncPort, MasterKeyPort
from coffer.domain.audit import AuditEventType
from coffer.domain.sync.errors import MasterKeyFileInvalid
from coffer.domain.sync.models import ExportSummary, ImportSummary


class SyncService:
    def __init__(
        self,
        *,
        exporter: SyncExporter,
        importer: SyncImporter,
        credentials: CredentialSyncPort,
        master_key: MasterKeyPort,
        audit: AuditService,
        bundle_factory: Callable[[Path], BundlePort],
    ) -> None:
        self._exporter = exporter
        self._importer = importer
        self._credentials = credentials
        self._master_key = master_key
        self._audit = audit
        self._bundle_factory = bundle_factory
        # Export and import both rewrite whole trees; serialize them so two
        # surfaces (CLI and UI) cannot interleave over the same vault.
        self._lock = asyncio.Lock()

    async def export_bundle(self, path: str, *, with_credentials: bool = False) -> ExportSummary:
        bundle = self._bundle_factory(Path(path).expanduser())
        async with self._lock:
            summary = await self._exporter.export(bundle, with_credentials=with_credentials)
        await self._audit.record(
            AuditEventType.SYNC_COMPLETED.value,
            actor="sync",
            details={
                "operation": "export",
                "path": summary.path,
                "credentials": with_credentials,
                "areas": {a.area: a.count for a in summary.areas},
                "failed": len(summary.failures),
            },
        )
        return summary

    async def import_bundle(self, path: str) -> ImportSummary:
        bundle = self._bundle_factory(Path(path).expanduser())
        async with self._lock:
            summary = await self._importer.import_(bundle)
        await self._audit.record(
            AuditEventType.SYNC_COMPLETED.value,
            actor="sync",
            details={
                "operation": "import",
                "path": summary.path,
                "areas": {a.area: a.count for a in summary.areas},
                "failed": len(summary.failures),
                "locked": len(summary.locked_refs),
            },
        )
        return summary

    def key_fingerprint(self) -> str | None:
        """A short SHA-256 fingerprint of the master key (never the key): two
        machines showing the same fingerprint hold the same key. None when no
        key exists on this machine yet."""
        key = self._master_key.export_key()
        if key is None:
            return None
        return hashlib.sha256(key).hexdigest()[:12]

    async def export_key(self, path: str) -> str:
        key = self._master_key.export_key()
        if key is None:
            raise MasterKeyFileInvalid(path, "no master key on this machine to export")
        target = Path(path).expanduser()
        await asyncio.to_thread(target.write_bytes, key)
        await asyncio.to_thread(target.chmod, 0o600)
        await self._audit.record(AuditEventType.MASTER_KEY_EXPORTED.value, actor="sync")
        return str(target)

    async def import_key(self, path: str) -> list[str]:
        """Install a key brought from another machine; returns the refs that
        are still locked afterwards (empty when everything decrypts here)."""
        source = Path(path).expanduser()
        if not source.exists():
            raise MasterKeyFileInvalid(path, "file does not exist")
        raw = await asyncio.to_thread(source.read_bytes)
        try:
            await asyncio.to_thread(self._master_key.install_key, raw)
        except ValueError as e:
            raise MasterKeyFileInvalid(path, "not a valid Fernet key") from e
        await self._audit.record(AuditEventType.MASTER_KEY_IMPORTED.value, actor="sync")
        return await asyncio.to_thread(self._credentials.locked_refs)
