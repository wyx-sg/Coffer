"""Putting one document's change into the vault (spec vault-sync ``## Applying a diff``).

One applier per bundle area, each owning a path prefix, each with exactly two
operations. Two rather than one "sync this path", because **removal is the
operation that had to be authorised** — import used to be forbidden from
deleting anything — and it should be visible at the seam rather than hidden
inside a branch.

Every applier raises ``CofferError`` to report a per-path failure. The round
catches it, holds the path so the next export cannot publish it as a deletion,
and carries on: one document that will not apply here is never allowed to stop
the rest.
"""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Mapping, Sequence

import yaml

from coffer.application.resource_service import ResourceService
from coffer.application.sync.ports import CredentialSyncPort, ImportGate, SyncedStatePort
from coffer.domain.error_base import CofferError
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource, ResourceRef
from coffer.domain.scope import Scope
from coffer.domain.sync.errors import SyncSerializationError
from coffer.domain.sync.fernet_time import is_fresher
from coffer.domain.sync.portability import expand_home


class TreeApplier:
    """``knowledge/`` and ``skills/`` — files, mirrored one path at a time.

    The file trees are the vault's own storage, so applying is a copy and
    removal is an unlink. No index to rebuild: the knowledge layer is a
    directory (ADR knowledge-is-plain-files), which is most of why bidirectional
    convergence is affordable at all.
    """

    def __init__(self, prefix: str, *, worktree: pathlib.Path, live_root: pathlib.Path) -> None:
        self.prefix = prefix
        self._worktree = worktree
        self._live_root = live_root

    async def upsert(self, path: str) -> None:
        await asyncio.to_thread(self._copy_in, path)

    async def remove(self, path: str) -> None:
        await asyncio.to_thread(self._unlink, path)

    def _relative(self, path: str) -> str:
        return path[len(self.prefix) :]

    def _copy_in(self, path: str) -> None:
        src = self._worktree / path
        if not src.is_file():
            raise SyncSerializationError(f"{path} is not a file in the working tree")
        dst = self._live_root / self._relative(path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())

    def _unlink(self, path: str) -> None:
        dst = self._live_root / self._relative(path)
        dst.unlink(missing_ok=True)
        # Leave no empty collection directory behind: a collection is a
        # directory, so an empty one is a collection that still exists.
        parent = dst.parent
        while parent != self._live_root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


class ResourceApplier:
    """``resources/<kind>/<name>.yaml`` — rows in the registry.

    Upsert runs the kind's import gate first, so a document that cannot apply
    on this machine is reported before anything is written. Removal goes
    through ``ResourceService.delete``, which releases the credentials no
    remaining resource cites — the orphaned-credential path that seeded the
    2026-07-10 clobber.
    """

    prefix = "resources/"

    def __init__(
        self,
        resources: ResourceService,
        *,
        worktree: pathlib.Path,
        gates: Sequence[ImportGate] = (),
        home: str | None,
        actor: str = "sync",
    ) -> None:
        self._resources = resources
        self._worktree = worktree
        self._gates = {gate.kind: gate for gate in gates}
        self._home = home
        self._actor = actor

    async def upsert(self, path: str) -> None:
        doc = await asyncio.to_thread(_read_yaml, self._worktree / path)
        kind, name = _ref_from(doc, path)
        raw_config = doc.get("config")
        config: dict[str, object] = dict(raw_config) if isinstance(raw_config, Mapping) else {}
        if self._home:
            config = expand_home(config, self._home)
        scope = Scope.from_json(doc.get("scope"))

        gate = self._gates.get(kind)
        if gate is not None:
            await gate.validate(config, scope=scope)

        ref = ResourceRef(kind, name)
        existing = await self._find(ref)
        raw_description = doc.get("description")
        description = raw_description if isinstance(raw_description, str) else None
        enabled = bool(doc.get("enabled", True))
        if existing is None:
            created = await self._resources.register(
                kind, name, config, self._actor, description=description, allow_lifecycle_kind=True
            )
            if not enabled:
                await self._resources.set_enabled(ref, False, self._actor)
            current_scope = created.scope
        else:
            await self._resources.update_config(
                ref,
                config,
                self._actor,
                description=description,
                allow_lifecycle_kind=True,
            )
            await self._resources.set_enabled(ref, enabled, self._actor)
            current_scope = existing.scope
        if scope != current_scope:
            await self._resources.update_scope(ref, scope, actor=self._actor)

    async def remove(self, path: str) -> None:
        kind, name = _ref_from({}, path)
        ref = ResourceRef(kind, name)
        if await self._find(ref) is None:
            # Already gone here — two machines deleting the same resource is
            # agreement, not a failure.
            return
        await self._resources.delete(ref, self._actor)

    async def _find(self, ref: ResourceRef) -> Resource | None:
        try:
            return await self._resources.get(ref)
        except ResourceNotFound:
            return None


class StateApplier:
    """``state/<area>/…`` — module-owned shared state.

    Dispatches to whichever provider claims the area. An area no provider
    claims is skipped rather than failed: it belongs to a module this build
    does not have, and refusing it every round would turn a version difference
    into a permanent error.
    """

    prefix = "state/"

    def __init__(self, providers: Sequence[SyncedStatePort], *, worktree: pathlib.Path) -> None:
        self._providers = {p.area: p for p in providers}
        self._worktree = worktree

    async def upsert(self, path: str) -> None:
        provider, rel = self._route(path)
        if provider is None:
            return
        doc = await asyncio.to_thread(_read_yaml, self._worktree / path)
        failures = await provider.import_docs([(rel, doc)])
        if failures:
            raise SyncSerializationError(f"{path}: {failures[0][1]}")

    async def remove(self, path: str) -> None:
        provider, rel = self._route(path)
        if provider is None:
            return
        await provider.delete_docs([rel])

    def _route(self, path: str) -> tuple[SyncedStatePort | None, str]:
        rest = path[len(self.prefix) :]
        area, _, rel = rest.partition("/")
        return self._providers.get(area), rel.removesuffix(".yaml")


class CredentialApplier:
    """``credentials/<ref>.enc`` — Fernet ciphertext, never the key.

    Guarded by encryption time even outside a merge conflict. A blob can reach
    this machine already stale — pushed cleanly by a machine that re-exported
    an older encryption — and writing it would orphan a working secret. The
    header is cleartext, so this costs nothing and needs no key.
    """

    prefix = "credentials/"

    def __init__(self, credentials: CredentialSyncPort, *, worktree: pathlib.Path) -> None:
        self._credentials = credentials
        self._worktree = worktree

    async def upsert(self, path: str) -> None:
        ref = self._ref(path)
        blob = await asyncio.to_thread((self._worktree / path).read_bytes)
        current = await asyncio.to_thread(self._credentials.read_ciphertext, ref)
        if current is not None and current != blob and not is_fresher(blob, current):
            return
        await asyncio.to_thread(self._credentials.write_ciphertext, ref, blob)

    async def remove(self, path: str) -> None:
        await asyncio.to_thread(self._credentials.delete_ciphertext, self._ref(path))

    def _ref(self, path: str) -> str:
        return path[len(self.prefix) :].removesuffix(".enc")


def _read_yaml(path: pathlib.Path) -> dict[str, object]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as e:
        raise SyncSerializationError(f"{path.name} could not be read: {e}") from e
    if not isinstance(raw, Mapping):
        raise SyncSerializationError(f"{path.name} is not a mapping")
    return dict(raw)


def _ref_from(doc: Mapping[str, object], path: str) -> tuple[str, str]:
    """Kind and name, from the document when it is there and the path when it
    is not — a removal has no document left to read."""
    kind, name = doc.get("kind"), doc.get("name")
    if isinstance(kind, str) and isinstance(name, str) and kind and name:
        return kind, name
    parts = path.split("/")
    if len(parts) != 3:
        raise SyncSerializationError(f"{path} is not resources/<kind>/<name>.yaml")
    return parts[1], parts[2].removesuffix(".yaml")


class ApplierError(CofferError):
    """Raised when no applier owns a path that the round expected one for."""

    code = "SYNC_APPLIER_MISSING"
