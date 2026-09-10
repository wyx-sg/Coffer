"""Apply an export bundle back into the local vault (spec and ADR vault-export-import).

Three rules, and no arbitration machinery behind them (there is no concurrent
writer — the user chose the direction when they ran the command):

* **The bundle wins.** Every resource the bundle holds overwrites the local one.
* **Import never deletes.** A resource the vault holds and the bundle does not
  is left untouched. A bundle is a snapshot of one machine, not an assertion
  about what should exist everywhere.
* **Per-resource failures are reported, not fatal.** A doc that cannot be
  applied here (an agent whose ``config_dir`` does not exist, say) lands in the
  summary with its ref and reason; every other doc still imports.

A bundle whose manifest declares a schema version this build does not know
fails closed before anything is touched.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from coffer.application.resource_service import ResourceService
from coffer.application.sync.ports import (
    BundlePort,
    CredentialSyncPort,
    ImportGate,
    PostImportHook,
    SyncedStatePort,
)
from coffer.domain.error_base import CofferError
from coffer.domain.resource import ResourceRef
from coffer.domain.sync.errors import SyncBundleTooNew
from coffer.domain.sync.manifest import SCHEMA_VERSION
from coffer.domain.sync.models import AreaCount, ImportSummary
from coffer.domain.sync.portability import expand_home
from coffer.domain.sync.serialization import ResourceDoc


class SyncImporter:
    def __init__(
        self,
        resources: ResourceService,
        credentials: CredentialSyncPort,
        *,
        actor: str = "sync",
        state_providers: Sequence[SyncedStatePort] = (),
        import_gates: Sequence[ImportGate] = (),
        post_import_hooks: Sequence[PostImportHook] = (),
        home: str | None,
    ) -> None:
        self._resources = resources
        self._credentials = credentials
        self._actor = actor
        self._state_providers = list(state_providers)
        self._gates = {gate.kind: gate for gate in import_gates}
        self._hooks = list(post_import_hooks)
        self._home = home

    async def import_(self, bundle: BundlePort) -> ImportSummary:
        summary = ImportSummary(path=bundle.path)
        # Version gate first: nothing is touched before we know we understand
        # the layout (spec vault-export-import "an older build refuses a newer bundle").
        await asyncio.to_thread(self._check_version, bundle)
        docs = [self._localize(doc) for doc in await asyncio.to_thread(bundle.read_resource_docs)]
        blobs = await asyncio.to_thread(bundle.read_credential_blobs)

        await asyncio.to_thread(bundle.mirror_trees_in)
        for subdir, count in await asyncio.to_thread(bundle.tree_counts):
            summary.areas.append(AreaCount(subdir, count))

        await self._import_credentials(blobs)
        applied = await self._reconcile_resources(docs, summary)
        summary.areas.append(AreaCount("resources", applied))
        await self._import_state(bundle, summary)
        if blobs:
            summary.areas.append(AreaCount("credentials", len(blobs)))

        # Rows are in; re-apply each kind's machine-local side-effects
        # (projections, native-config transforms, deliveries) from current
        # state, so an imported resource is as usable as a hand-registered
        # one. A hook that RAISES must not lose the rows already applied.
        for hook in self._hooks:
            try:
                messages = await hook.reconcile()
            except Exception as e:
                messages = [str(e)]
            for message in messages:
                summary.failures.append((f"reconcile[{hook.kind}]", message))

        summary.locked_refs = await asyncio.to_thread(self._credentials.locked_refs)
        return summary

    def _check_version(self, bundle: BundlePort) -> None:
        bundle.require_readable()
        manifest = bundle.read_manifest()
        if manifest is not None and manifest.schema_version > SCHEMA_VERSION:
            raise SyncBundleTooNew(manifest.schema_version, SCHEMA_VERSION)

    def _localize(self, doc: ResourceDoc) -> ResourceDoc:
        """Bundle doc -> this machine's view: expand ``${HOME}``."""
        if not self._home:
            return doc
        return ResourceDoc(
            kind=doc.kind,
            name=doc.name,
            description=doc.description,
            enabled=doc.enabled,
            config=expand_home(doc.config, self._home),
            # Scope names agents, never paths — threaded through verbatim.
            scope=doc.scope,
        )

    async def _import_credentials(self, blobs: dict[str, bytes]) -> None:
        """Ciphertext only, and the bundle wins. A machine that holds the
        blobs but not the master key reports them locked (below) rather than
        silently failing decryption."""
        for ref, blob in blobs.items():
            await asyncio.to_thread(self._credentials.write_ciphertext, ref, blob)

    async def _import_state(self, bundle: BundlePort, summary: ImportSummary) -> None:
        # After resources, so a doc referencing a just-imported channel binds.
        for provider in self._state_providers:
            docs = await asyncio.to_thread(bundle.read_state_docs, provider.area)
            try:
                failures = await provider.import_docs(docs)
            except Exception as e:
                summary.failures.append((f"state/{provider.area}", str(e)))
                continue
            for path, message in failures:
                summary.failures.append((f"state/{provider.area}/{path}", message))
            summary.areas.append(AreaCount(f"state/{provider.area}", len(docs) - len(failures)))

    async def _reconcile_resources(self, docs: list[ResourceDoc], summary: ImportSummary) -> int:
        current = {(r.kind, r.name): r for r in await self._resources.list()}
        applied = 0
        for doc in docs:
            ref = ResourceRef(doc.kind, doc.name)
            try:
                # Import gate: machine-local preconditions (an agent's config
                # dir must exist HERE). A gate failure is reported like any
                # other per-resource failure and never stops the bundle.
                gate = self._gates.get(doc.kind)
                if gate is not None:
                    await gate.validate(doc.config, scope=doc.scope)
                existing = current.get((doc.kind, doc.name))
                if existing is not None:
                    await self._resources.update_config(
                        ref,
                        doc.config,
                        self._actor,
                        description=doc.description,
                        allow_lifecycle_kind=True,
                    )
                    await self._resources.set_enabled(ref, doc.enabled, self._actor)
                    row_scope = existing.scope
                else:
                    created = await self._resources.register(
                        doc.kind,
                        doc.name,
                        doc.config,
                        self._actor,
                        description=doc.description,
                        allow_lifecycle_kind=True,
                    )
                    if not doc.enabled:
                        await self._resources.set_enabled(ref, False, self._actor)
                    # register() applies the kind's own registration default,
                    # so read the row's actual scope back rather than assuming.
                    row_scope = created.scope
                if doc.scope != row_scope:
                    await self._resources.update_scope(ref, doc.scope, actor=self._actor)
                applied += 1
            except CofferError as e:
                summary.failures.append((f"{doc.kind}:{doc.name}", str(e)))
        return applied
