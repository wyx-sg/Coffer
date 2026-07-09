"""Apply merged workspace state back into the local vault (spec 010).

Runs after a clean git merge: the workspace holds the union of every machine's
state. Import reconciles the local vault to match it — upserting resources,
applying explicit tombstones, and importing ciphertext. A resource merely
absent from the workspace is NEVER deleted (a failed import elsewhere must not
masquerade as a deletion); deletion happens only via tombstone.

Per-resource failures (e.g. an agent whose config dir does not exist on this
machine) are QUARANTINED, not fatal and not dropped: the ref is reported in
sync state, its workspace doc is preserved verbatim by the next export, and the
import retries every run.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field

from coffer.application.resource_service import ResourceService
from coffer.application.sync.ports import CredentialSyncPort, SyncedStatePort, WorkspacePort
from coffer.domain.error_base import CofferError
from coffer.domain.resource import ResourceRef
from coffer.domain.sync.errors import SyncWorkspaceTooNew
from coffer.domain.sync.manifest import SCHEMA_VERSION
from coffer.domain.sync.models import Tombstone
from coffer.domain.sync.portability import apply_merge_patch, expand_home
from coffer.domain.sync.serialization import ResourceDoc


@dataclass
class ImportResult:
    applied: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)
    locked_refs: list[str] = field(default_factory=list)
    quarantined_refs: list[str] = field(default_factory=list)
    failed_state_paths: list[str] = field(default_factory=list)


class SyncImporter:
    def __init__(
        self,
        resources: ResourceService,
        credentials: CredentialSyncPort,
        workspace: WorkspacePort,
        *,
        actor: str = "sync",
        state_providers: Sequence[SyncedStatePort] = (),
        home: str | None,
    ) -> None:
        self._resources = resources
        self._credentials = credentials
        self._workspace = workspace
        self._actor = actor
        self._state_providers = list(state_providers)
        self._home = home

    async def import_(self, machine_id: str | None = None) -> ImportResult:
        docs, tombstones, blobs = await asyncio.to_thread(self._load)
        overrides = (
            await asyncio.to_thread(self._workspace.read_overrides, machine_id)
            if machine_id
            else {}
        )
        docs = [self._localize(doc, overrides) for doc in docs]
        result = ImportResult()
        await self._import_credentials(blobs, result)
        await self._apply_tombstones(tombstones, docs, result)
        await self._reconcile_resources(docs, result)
        await self._import_state(result)
        result.locked_refs = await asyncio.to_thread(self._credentials.locked_refs)
        return result

    async def _import_state(self, result: ImportResult) -> None:
        # After resources, so a doc referencing a just-imported channel binds.
        for provider in self._state_providers:
            docs = await asyncio.to_thread(self._workspace.read_state_docs, provider.area)
            for path, message in await provider.import_docs(docs):
                result.errors.append(f"{provider.area}/{path}: {message}")
                result.failed_state_paths.append(f"{provider.area}/{path}")

    def _localize(
        self, doc: ResourceDoc, overrides: dict[tuple[str, str], dict[str, object]]
    ) -> ResourceDoc:
        """Shared doc -> this machine's view: expand ${HOME}, apply own patch."""
        config = dict(doc.config)
        if self._home:
            config = expand_home(config, self._home)
        patch = overrides.get((doc.kind, doc.name))
        if patch:
            config = apply_merge_patch(config, patch)
        return ResourceDoc(
            kind=doc.kind,
            name=doc.name,
            description=doc.description,
            enabled=doc.enabled,
            config=config,
        )

    def _load(self) -> tuple[list[ResourceDoc], list[Tombstone], dict[str, bytes]]:
        manifest = self._workspace.read_manifest()
        if manifest is not None and manifest.schema_version > SCHEMA_VERSION:
            raise SyncWorkspaceTooNew(manifest.schema_version, SCHEMA_VERSION)
        self._workspace.mirror_trees_in()
        return (
            self._workspace.read_resource_docs(),
            self._workspace.read_tombstones(),
            self._workspace.read_credential_blobs(),
        )

    async def _import_credentials(self, blobs: dict[str, bytes], result: ImportResult) -> None:
        for ref, blob in blobs.items():
            await asyncio.to_thread(self._credentials.write_ciphertext, ref, blob)

    async def _apply_tombstones(
        self, tombstones: list[Tombstone], docs: list[ResourceDoc], result: ImportResult
    ) -> None:
        """Delete local resources named by a tombstone.

        When a resource doc and a tombstone coexist for the same ref (merge
        artifact of a delete racing a re-create), the doc wins — the deleting
        machine's next export clears the stale tombstone."""
        alive = {(d.kind, d.name) for d in docs}
        current = {(r.kind, r.name) for r in await self._resources.list()}
        for tombstone in tombstones:
            key = (tombstone.kind, tombstone.name)
            if key in alive or key not in current:
                continue
            try:
                await self._resources.delete(
                    ResourceRef(tombstone.kind, tombstone.name), self._actor
                )
                result.deleted += 1
            except CofferError as e:
                result.errors.append(f"{tombstone.kind}:{tombstone.name} (delete): {e}")

    async def _reconcile_resources(self, docs: list[ResourceDoc], result: ImportResult) -> None:
        current = {(r.kind, r.name): r for r in await self._resources.list()}

        for doc in docs:
            ref = ResourceRef(doc.kind, doc.name)
            try:
                if (doc.kind, doc.name) in current:
                    await self._resources.update_config(
                        ref,
                        doc.config,
                        self._actor,
                        description=doc.description,
                        allow_lifecycle_kind=True,
                    )
                    await self._resources.set_enabled(ref, doc.enabled, self._actor)
                else:
                    await self._resources.register(
                        doc.kind,
                        doc.name,
                        doc.config,
                        self._actor,
                        description=doc.description,
                        allow_lifecycle_kind=True,
                    )
                    if not doc.enabled:
                        await self._resources.set_enabled(ref, False, self._actor)
                result.applied += 1
            except CofferError:
                # Quarantined, not fatal: reported in sync state, preserved by
                # the next export, retried on every run.
                result.quarantined_refs.append(f"{doc.kind}:{doc.name}")
