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
from datetime import UTC, datetime

from coffer.application.resource_service import ResourceService
from coffer.application.sync.ports import (
    CredentialSyncPort,
    ImportGate,
    PostImportHook,
    SyncedStatePort,
    WorkspacePort,
)
from coffer.domain.error_base import CofferError
from coffer.domain.resource import ResourceRef
from coffer.domain.sync.errors import SyncWorkspaceTooNew
from coffer.domain.sync.fernet_time import fernet_created_at, is_staler
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
        import_gates: Sequence[ImportGate] = (),
        post_import_hooks: Sequence[PostImportHook] = (),
        home: str | None,
    ) -> None:
        self._resources = resources
        self._credentials = credentials
        self._workspace = workspace
        self._actor = actor
        self._state_providers = list(state_providers)
        self._gates = {gate.kind: gate for gate in import_gates}
        self._hooks = list(post_import_hooks)
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
        tombstoned = {t.name: _aware(t.deleted_at) for t in tombstones if t.kind == "credential"}
        await self._import_credentials(blobs, tombstoned, result)
        await self._apply_tombstones(tombstones, docs, result)
        await self._reconcile_resources(docs, result)
        await self._import_state(result)
        # Rows are converged; re-apply each kind's machine-local side-effects
        # (projections, native-config transforms, deliveries) from current
        # state. Failures surface in the run and retry on the next import —
        # including a hook that RAISES: the rows already applied, so the
        # import result must survive it.
        for hook in self._hooks:
            try:
                messages = await hook.reconcile()
            except Exception as e:
                messages = [str(e)]
            for message in messages:
                result.errors.append(f"reconcile[{hook.kind}]: {message}")
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
            # Scope holds machine ULIDs / agent names, never paths — threaded
            # through verbatim, no ${HOME} expansion or override patch.
            scope=doc.scope,
            scope_present=doc.scope_present,
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

    async def _import_credentials(
        self, blobs: dict[str, bytes], tombstoned: dict[str, datetime], result: ImportResult
    ) -> None:
        for ref, blob in blobs.items():
            deleted_at = tombstoned.get(ref)
            if deleted_at is not None and not _encrypted_after(blob, deleted_at):
                # Tombstoned and not re-created since: a stray blob file (e.g.
                # resurrected by a merge the deleting machine hasn't pruned
                # yet) must not re-enter the vault.
                continue
            existing = await asyncio.to_thread(self._credentials.read_ciphertext, ref)
            if existing is not None and is_staler(blob, existing):
                # Workspace holds an older encryption of this ref (e.g. pushed
                # by a machine without freshness guards) — keep the local one;
                # the next export heals the medium.
                continue
            await asyncio.to_thread(self._credentials.write_ciphertext, ref, blob)

    async def _apply_credential_tombstone(self, tombstone: Tombstone, result: ImportResult) -> None:
        """Delete the local credential row named by a tombstone.

        A blob whose embedded encryption time postdates the tombstone was
        re-created after the deletion — resurrection wins, mirroring the
        doc-beats-tombstone rule for resources."""
        blob = await asyncio.to_thread(self._credentials.read_ciphertext, tombstone.name)
        if blob is None:
            return
        if _encrypted_after(blob, _aware(tombstone.deleted_at)):
            return
        await asyncio.to_thread(self._credentials.delete_ciphertext, tombstone.name)
        result.deleted += 1

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
            if tombstone.kind == "credential":
                await self._apply_credential_tombstone(tombstone, result)
                continue
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
                # Import gate: machine-local preconditions (an agent's config
                # dir must exist HERE). A gate failure quarantines like any
                # other import failure and self-heals on a later run.
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
                    # register() applies the kind's own registration default
                    # (e.g. channel's dormant `{}`, not None) — read it back
                    # off the created row rather than assuming None, or a
                    # scope-silent doc (see below) would wrongly appear to
                    # "mismatch" a kind default it was never meant to touch.
                    row_scope = created.scope
                # A pre-v4 doc (scope key absent entirely) carries no opinion
                # on scope at all — never reconcile, so a locally-scoped
                # channel stays exactly as it is. This is different from an
                # explicit `scope: null`, which IS an opinion (unscoped) and
                # does win. Compare against the row's ACTUAL current scope
                # (existing row, or the just-registered row's kind-default) —
                # never a hardcoded None — and only write on a real mismatch.
                if doc.scope_present and doc.scope != row_scope:
                    await self._resources.update_scope(ref, doc.scope, actor=self._actor)
                result.applied += 1
            except CofferError:
                # Quarantined, not fatal: reported in sync state, preserved by
                # the next export, retried on every run.
                result.quarantined_refs.append(f"{doc.kind}:{doc.name}")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _encrypted_after(blob: bytes, moment: datetime) -> bool:
    ts = fernet_created_at(blob)
    return ts is not None and datetime.fromtimestamp(ts, tz=UTC) > moment
