"""Export local vault state into the sync workspace (spec 010)."""

from __future__ import annotations

import asyncio

from coffer.application.resource_service import ResourceService
from coffer.application.sync.ports import CredentialSyncPort, WorkspacePort
from coffer.domain.sync.manifest import Manifest
from coffer.domain.sync.serialization import resource_to_doc


class SyncExporter:
    """Writes resources, file trees, ciphertext, and the manifest to the workspace."""

    def __init__(
        self,
        resources: ResourceService,
        credentials: CredentialSyncPort,
        workspace: WorkspacePort,
    ) -> None:
        self._resources = resources
        self._credentials = credentials
        self._workspace = workspace

    async def export(self) -> None:
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
        # All filesystem + raw-sqlite IO runs off the event loop.
        await asyncio.to_thread(self._dump, docs)

    def _dump(self, docs: list[dict[str, object]]) -> None:
        self._workspace.write_resource_docs(docs)
        self._workspace.mirror_trees_out()
        blobs: dict[str, bytes] = {}
        for ref in self._credentials.list_refs():
            blob = self._credentials.read_ciphertext(ref)
            if blob is not None:
                blobs[ref] = blob
        self._workspace.write_credential_blobs(blobs)
        self._workspace.write_manifest(Manifest())
