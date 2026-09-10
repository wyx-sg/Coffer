"""Write local vault state into an export bundle (spec and ADR vault-export-import).

An export is a snapshot of THIS vault at THIS moment: the bundle directory is
cleared and rewritten, so what comes out is exactly what is here. There is no
remote to reconcile against, so there are no tombstones, no timestamp
arbitration, and no "not yet ingested" guards — those existed only to keep two
live vaults convergent.

Credentials are omitted unless the caller explicitly asks for them, and even
then only Fernet ciphertext travels; the master key is never written.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from coffer.application.resource_service import ResourceService
from coffer.application.sync.ports import BundlePort, CredentialSyncPort, SyncedStatePort
from coffer.domain.sync.manifest import Manifest
from coffer.domain.sync.models import AreaCount, ExportSummary
from coffer.domain.sync.portability import normalize_home
from coffer.domain.sync.serialization import resource_to_doc


class SyncExporter:
    """Writes the manifest, mirrored trees, resource docs, shared state, and
    (opt-in) credential ciphertext into a bundle directory."""

    def __init__(
        self,
        resources: ResourceService,
        credentials: CredentialSyncPort,
        state_providers: Sequence[SyncedStatePort] = (),
        *,
        home: str | None,
    ) -> None:
        self._resources = resources
        self._credentials = credentials
        self._state_providers = list(state_providers)
        self._home = home

    async def export(self, bundle: BundlePort, *, with_credentials: bool = False) -> ExportSummary:
        summary = ExportSummary(path=bundle.path, credentials_included=with_credentials)
        docs: list[dict[str, object]] = []
        for r in await self._resources.list():
            try:
                config = dict(r.config)
                # The bundle speaks ${HOME}, never this machine's literal home.
                if self._home:
                    config = normalize_home(config, self._home)
                docs.append(
                    resource_to_doc(
                        kind=r.kind,
                        name=r.name,
                        description=r.description,
                        enabled=r.enabled,
                        config=config,
                        # Scope names agents, never paths — it rides verbatim.
                        scope=r.scope,
                    )
                )
            except Exception as e:  # a single unserializable row is reported, not fatal
                summary.failures.append((f"{r.kind}:{r.name}", str(e)))

        state_docs: list[tuple[str, list[tuple[str, dict[str, object]]]]] = []
        for provider in self._state_providers:
            try:
                area_docs, _owned = await provider.export_docs()
            except Exception as e:
                summary.failures.append((f"state/{provider.area}", str(e)))
                continue
            state_docs.append((provider.area, area_docs))

        blobs: dict[str, bytes] = {}
        if with_credentials:
            for ref in await asyncio.to_thread(self._credentials.list_refs):
                blob = await asyncio.to_thread(self._credentials.read_ciphertext, ref)
                if blob is not None:
                    blobs[ref] = blob

        # All filesystem IO runs off the event loop.
        await asyncio.to_thread(self._dump, bundle, docs, state_docs, blobs)

        summary.areas.append(AreaCount("resources", len(docs)))
        for subdir, count in await asyncio.to_thread(bundle.tree_counts):
            summary.areas.append(AreaCount(subdir, count))
        for area, area_docs in state_docs:
            summary.areas.append(AreaCount(f"state/{area}", len(area_docs)))
        if with_credentials:
            summary.areas.append(AreaCount("credentials", len(blobs)))
        return summary

    def _dump(
        self,
        bundle: BundlePort,
        docs: list[dict[str, object]],
        state_docs: list[tuple[str, list[tuple[str, dict[str, object]]]]],
        blobs: dict[str, bytes],
    ) -> None:
        bundle.open_for_write()
        bundle.write_manifest(Manifest())
        bundle.write_resource_docs(docs)
        for area, area_docs in state_docs:
            bundle.write_state_docs(area, area_docs)
        bundle.mirror_trees_out()
        if blobs:
            bundle.write_credential_blobs(blobs)
