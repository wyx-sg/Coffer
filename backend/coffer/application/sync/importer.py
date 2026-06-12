"""Apply merged workspace state back into the local vault (spec 010).

Runs after a clean git merge: the workspace already holds the *union* of every
machine's state (export writes local state before the merge, so local-only
additions survive and deletions propagate through git). Import therefore
reconciles the local vault to exactly match the workspace.

Per-resource failures (e.g. an agent whose config dir does not exist on this
machine) are collected, not fatal — one unportable row must not block syncing
everything else.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from coffer.application.resource_service import ResourceService
from coffer.application.sync.ports import CredentialSyncPort, WorkspacePort
from coffer.domain.error_base import CofferError
from coffer.domain.resource import ResourceRef
from coffer.domain.sync.serialization import ResourceDoc


@dataclass
class ImportResult:
    applied: int = 0
    deleted: int = 0
    errors: list[str] = field(default_factory=list)
    locked_refs: list[str] = field(default_factory=list)


class SyncImporter:
    def __init__(
        self,
        resources: ResourceService,
        credentials: CredentialSyncPort,
        workspace: WorkspacePort,
        *,
        actor: str = "sync",
    ) -> None:
        self._resources = resources
        self._credentials = credentials
        self._workspace = workspace
        self._actor = actor

    async def import_(self) -> ImportResult:
        docs, blobs = await asyncio.to_thread(self._load)
        result = ImportResult()
        await self._import_credentials(blobs, result)
        await self._reconcile_resources(docs, result)
        result.locked_refs = await asyncio.to_thread(self._credentials.locked_refs)
        return result

    def _load(self) -> tuple[list[ResourceDoc], dict[str, bytes]]:
        self._workspace.mirror_trees_in()
        return self._workspace.read_resource_docs(), self._workspace.read_credential_blobs()

    async def _import_credentials(self, blobs: dict[str, bytes], result: ImportResult) -> None:
        for ref, blob in blobs.items():
            await asyncio.to_thread(self._credentials.write_ciphertext, ref, blob)

    async def _reconcile_resources(
        self, docs: list[ResourceDoc], result: ImportResult
    ) -> None:
        current = {(r.kind, r.name): r for r in await self._resources.list()}
        wanted: set[tuple[str, str]] = set()

        for doc in docs:
            wanted.add((doc.kind, doc.name))
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
            except CofferError as e:
                result.errors.append(f"{ref}: {e}")

        # Deletions: a resource gone from the merged workspace was deleted upstream.
        for (kind, name), _resource in current.items():
            if (kind, name) not in wanted:
                try:
                    await self._resources.delete(ResourceRef(kind, name), self._actor)
                    result.deleted += 1
                except CofferError as e:
                    result.errors.append(f"{kind}:{name} (delete): {e}")
