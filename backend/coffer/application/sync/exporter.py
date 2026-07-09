"""Export local vault state into the sync workspace (spec 010)."""

from __future__ import annotations

import asyncio
from collections.abc import Collection
from datetime import UTC, datetime, timedelta

from coffer.application.resource_service import ResourceService
from coffer.application.sync.ports import CredentialSyncPort, TombstoneLedgerPort, WorkspacePort
from coffer.domain.sync.manifest import Manifest
from coffer.domain.sync.models import TOMBSTONE_TTL_SECONDS, Tombstone
from coffer.domain.sync.serialization import resource_to_doc


class SyncExporter:
    """Writes resources, file trees, ciphertext, tombstones, and the manifest."""

    def __init__(
        self,
        resources: ResourceService,
        credentials: CredentialSyncPort,
        workspace: WorkspacePort,
        ledger: TombstoneLedgerPort | None = None,
    ) -> None:
        self._resources = resources
        self._credentials = credentials
        self._workspace = workspace
        self._ledger = ledger

    async def export(
        self, *, quarantined: Collection[str] = (), machine_id: str | None = None
    ) -> None:
        resources = await self._resources.list()
        docs = [
            resource_to_doc(
                kind=r.kind,
                name=r.name,
                description=r.description,
                enabled=r.enabled,
                config=r.config,
            )
            for r in resources
        ]
        live = {(r.kind, r.name) for r in resources}
        pending = await self._reconcile_ledger(live)
        # All filesystem + raw-sqlite IO runs off the event loop.
        await asyncio.to_thread(self._dump, docs, live, pending, set(quarantined), machine_id)

    async def _reconcile_ledger(self, live: set[tuple[str, str]]) -> list[Tombstone]:
        """Ledger rows for re-registered or expired resources are dropped; the
        rest become workspace tombstones."""
        if self._ledger is None:
            return []
        cutoff = datetime.now(tz=UTC) - timedelta(seconds=TOMBSTONE_TTL_SECONDS)
        await self._ledger.prune_older_than(cutoff)
        pending: list[Tombstone] = []
        for tombstone in await self._ledger.list():
            if (tombstone.kind, tombstone.name) in live:
                await self._ledger.remove(tombstone.kind, tombstone.name)
            else:
                pending.append(tombstone)
        return pending

    def _dump(
        self,
        docs: list[dict[str, object]],
        live: set[tuple[str, str]],
        pending: list[Tombstone],
        quarantined: set[str],
        machine_id: str | None,
    ) -> None:
        self._workspace.write_resource_docs(docs, preserve=quarantined)
        self._sync_tombstone_files(live, pending, machine_id)
        self._workspace.mirror_trees_out()
        blobs: dict[str, bytes] = {}
        for ref in self._credentials.list_refs():
            blob = self._credentials.read_ciphertext(ref)
            if blob is not None:
                blobs[ref] = blob
        self._workspace.write_credential_blobs(blobs)
        self._workspace.write_manifest(Manifest())

    def _sync_tombstone_files(
        self,
        live: set[tuple[str, str]],
        pending: list[Tombstone],
        machine_id: str | None,
    ) -> None:
        """Reconcile ``tombstones/`` with reality.

        A tombstone present at export time was applied locally in an earlier
        import — so a live resource with the same ref means the user re-created
        it afterwards and the tombstone must go (re-registration wins). Expired
        tombstones are pruned the same way. Fresh local deletions are written
        with this machine as provenance."""
        cutoff = datetime.now(tz=UTC) - timedelta(seconds=TOMBSTONE_TTL_SECONDS)
        kept: set[tuple[str, str]] = set()
        for existing in self._workspace.read_tombstones():
            ts = existing.deleted_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            if (existing.kind, existing.name) in live or ts < cutoff:
                self._workspace.remove_tombstone(existing.kind, existing.name)
            else:
                kept.add((existing.kind, existing.name))
        for tombstone in pending:
            # An existing tombstone wins: import-applied deletions also land in
            # the local ledger, and rewriting the file here would churn its
            # provenance/timestamp on every machine that imports the delete.
            if (tombstone.kind, tombstone.name) in kept:
                continue
            self._workspace.write_tombstone(
                Tombstone(
                    kind=tombstone.kind,
                    name=tombstone.name,
                    deleted_at=tombstone.deleted_at,
                    by=machine_id,
                )
            )
