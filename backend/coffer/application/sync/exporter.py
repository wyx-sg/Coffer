"""Export local vault state into the sync workspace (spec 010).

Tombstone reconciliation is timestamp-based: a live resource supersedes a
tombstone only when it was (re-)created AFTER the deletion. A live row that
PREDATES a workspace tombstone means the deletion was merged but not yet
applied locally (e.g. a run interrupted between pull and import) — its doc is
withheld from the export and the tombstone kept, so an interrupted run can
never resurrect a deletion on the other machines.
"""

from __future__ import annotations

import asyncio
from collections.abc import Collection
from datetime import UTC, datetime, timedelta

from coffer.application.resource_service import ResourceService
from coffer.application.sync.ports import CredentialSyncPort, TombstoneLedgerPort, WorkspacePort
from coffer.domain.sync.manifest import SCHEMA_VERSION, Manifest
from coffer.domain.sync.models import TOMBSTONE_TTL_SECONDS, Tombstone
from coffer.domain.sync.serialization import resource_to_doc


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=UTC)


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
        live = {(r.kind, r.name): _aware(r.created_at) for r in resources}
        pending = await self._reconcile_ledger(live, set(quarantined))
        # All filesystem + raw-sqlite IO runs off the event loop.
        await asyncio.to_thread(self._dump, docs, live, pending, set(quarantined), machine_id)

    async def _reconcile_ledger(
        self, live: dict[tuple[str, str], datetime], quarantined: set[str]
    ) -> list[Tombstone]:
        """The ledger holds this machine's own deletions. Rows superseded by a
        later re-creation, by a quarantined workspace doc (the remote re-created
        something we can't even import), or by the TTL are dropped; the rest
        become workspace tombstones."""
        if self._ledger is None:
            return []
        cutoff = datetime.now(tz=UTC) - timedelta(seconds=TOMBSTONE_TTL_SECONDS)
        await self._ledger.prune_older_than(cutoff)
        pending: list[Tombstone] = []
        for tombstone in await self._ledger.list():
            key = (tombstone.kind, tombstone.name)
            created = live.get(key)
            recreated = created is not None and created > _aware(tombstone.deleted_at)
            if recreated or f"{tombstone.kind}:{tombstone.name}" in quarantined:
                await self._ledger.remove(tombstone.kind, tombstone.name)
            else:
                pending.append(tombstone)
        return pending

    def _dump(
        self,
        docs: list[dict[str, object]],
        live: dict[tuple[str, str], datetime],
        pending: list[Tombstone],
        quarantined: set[str],
        machine_id: str | None,
    ) -> None:
        withheld = self._sync_tombstone_files(live, pending, machine_id)
        kept_docs = [d for d in docs if (str(d["kind"]), str(d["name"])) not in withheld]
        self._workspace.write_resource_docs(kept_docs, preserve=quarantined)
        self._workspace.mirror_trees_out()
        blobs: dict[str, bytes] = {}
        for ref in self._credentials.list_refs():
            blob = self._credentials.read_ciphertext(ref)
            if blob is not None:
                blobs[ref] = blob
        self._workspace.write_credential_blobs(blobs)
        self._write_manifest_guarded()

    def _write_manifest_guarded(self) -> None:
        """Never downgrade a manifest written by a newer build — overwriting it
        would silently disarm the ``SYNC_WORKSPACE_TOO_NEW`` gate on the next
        run and push the downgraded manifest back to every machine."""
        existing = self._workspace.read_manifest()
        if existing is not None and existing.schema_version > SCHEMA_VERSION:
            return
        self._workspace.write_manifest(Manifest())

    def _sync_tombstone_files(
        self,
        live: dict[tuple[str, str], datetime],
        pending: list[Tombstone],
        machine_id: str | None,
    ) -> set[tuple[str, str]]:
        """Reconcile ``tombstones/`` with reality; returns the refs whose live
        rows are STALER than their tombstone (deletion merged but not yet
        applied locally) — their docs must be withheld from this export."""
        now = datetime.now(tz=UTC)
        cutoff = now - timedelta(seconds=TOMBSTONE_TTL_SECONDS)
        kept: set[tuple[str, str]] = set()
        withheld: set[tuple[str, str]] = set()
        for existing in self._workspace.read_tombstones():
            key = (existing.kind, existing.name)
            deleted_at = _aware(existing.deleted_at)
            created = live.get(key)
            if created is not None and created > deleted_at:
                # Genuinely re-created after the deletion: resurrection wins.
                self._workspace.remove_tombstone(existing.kind, existing.name)
            elif deleted_at < cutoff:
                self._workspace.remove_tombstone(existing.kind, existing.name)
            else:
                kept.add(key)
                if created is not None:
                    withheld.add(key)
        for tombstone in pending:
            # An existing tombstone wins: rewriting it here would churn its
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
        return withheld
