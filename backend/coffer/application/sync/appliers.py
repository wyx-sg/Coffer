"""Putting one document's change into the vault (spec vault-sync ``## Applying a diff``).

One applier per bundle area, each owning a path prefix, each with exactly two
operations. Two rather than one "sync this path", because **removal is the
operation that had to be authorised** — the one-way import this replaced was
forbidden from deleting anything — and it should be visible at the seam rather
than hidden inside a branch.

A path no applier owns is not a failure and needs no error of its own:
``machines/`` and ``manifest.json`` are in every diff and belong to nobody,
which is why ``convergence_ops.applier_for`` answers with ``None`` and the
round skips the path.

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
from coffer.domain.errors import ResourceNotFound
from coffer.domain.resource import Resource
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
        if src.is_symlink():
            # Whatever it points at is not vault content. A remote that
            # committed a link to ``/etc/passwd`` must not have it read here.
            raise SyncSerializationError(f"{path} is a symlink in the working tree")
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
    """``resources/<kind>/<uid>.yaml`` — rows in the registry.

    **The path is the resource's uid, and that is what makes a rename safe**
    (ADR resource-identity-is-an-immutable-uid). The identity is immutable, so
    the path is stable across everything the user can change; a rename reaches
    this applier as an ``upsert`` of a path that was already there, carrying a
    different ``name`` inside. Keyed on the name, the same edit arrived as a
    ``remove`` of one path beside an ``upsert`` of another, and the ``remove``
    below is not a bookkeeping nicety — it runs the real
    ``ResourceService.delete``, whose cascade takes the kind-owned state
    (paired chats, capability preferences, skill bindings) and whose
    orphaned-credential release takes the secret nothing else cites. A rename
    was therefore destructive or survivable according to whether the new name
    sorted before or after the old one in the path-ordered apply loop.

    Upsert runs the kind's import gate first, so a document that cannot apply
    on this machine is reported before anything is written. Removal goes
    through ``ResourceService.delete``, which releases the credentials no
    remaining resource cites — the orphaned-credential path that seeded the
    2026-07-10 clobber.

    What an incoming document may change is narrower than what it used to be.
    It carries the resource — identity, description, config — and it does not
    carry the resource's **reach**: ``enabled`` and ``scope`` are one decision
    the user makes per machine, on the machine, and an arriving document never
    touches them here. A row that already exists keeps the reach it was given; a row
    that has just arrived takes the framework's own default, because a resource
    nobody on this machine has looked at yet has not been given a reach here
    either.

    A document of a kind that declares ``converges=False`` is ignored outright,
    upsert and removal alike. The exporter already withholds those, so this end
    of the rule only matters while the fleet is mixed — but that is exactly
    when it matters: a machine still on an older build keeps publishing them,
    and without this the ghost row arrives from the one direction the export
    fix cannot reach. Removal is skipped for the opposite reason: a derived row
    here was computed from THIS machine's agents, so a deletion in the tree has
    no standing over it.
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
        uid, kind, name = _identity_from(doc, path)
        raw_config = doc.get("config")
        config: dict[str, object] = dict(raw_config) if isinstance(raw_config, Mapping) else {}
        if self._home:
            config = expand_home(config, self._home)

        if not self._resources.converges(kind):
            return

        gate = self._gates.get(kind)
        if gate is not None:
            # The gate sees the config alone. It used to be handed the
            # document's scope as well, so a scope-aware gate could wave a
            # dormant doc past a machine-local precondition; reach does not
            # travel any more, and a gate that still wants that leniency reads
            # this machine's own row for it — the only place the answer was
            # ever true.
            await gate.validate(config)

        # By uid, never by name. The row this document is about is the row
        # that shares its identity, and a row with the same *name* may well be
        # a different resource someone created here independently — which is a
        # collision to report, not a row to overwrite.
        existing = await self._find(uid)
        raw_description = doc.get("description")
        description = raw_description if isinstance(raw_description, str) else None
        if existing is None:
            # Registered at the identity the document carries rather than a
            # fresh one, so both machines go on holding the same resource. A
            # uid minted here would make this machine's copy a *different*
            # resource that happens to look the same, and the next round would
            # publish it as one.
            #
            # Whatever reach the framework gives a fresh row — the kind's
            # ``default_scope`` and the ``enabled`` default — is the right one.
            # This resource has just arrived; nobody on THIS machine has said
            # yet how far it should reach, and inventing an answer from the
            # other machine's would be exactly the silent re-answering the
            # document stopped carrying reach to prevent.
            await self._resources.register(
                kind,
                name,
                config,
                self._actor,
                description=description,
                allow_lifecycle_kind=True,
                uid=uid,
            )
        else:
            # A document that arrives at an identity this machine already
            # holds, spelling a different name, is a RENAME — not a new
            # resource, and not a name to ignore. It is a rename because the
            # identity is the uid: the user changed a label on the machine
            # they were sitting at, and the same resource is still the same
            # resource. Applying it through ``rename`` rather than writing the
            # column is what gives the kind its ``on_rename`` hook, so a kind
            # whose name is also a directory on disk moves that directory here
            # too — which is the whole reason the hook exists.
            if existing.name != name:
                await self._resources.rename(uid, name, self._actor)
            # Config and description only. The local ``enabled`` and ``scope``
            # are left exactly as this machine set them — that is the whole
            # decision, and it is a decision about *this* machine that an
            # incoming document has no standing to revise.
            await self._resources.update_config(
                uid,
                config,
                self._actor,
                description=description,
                allow_lifecycle_kind=True,
            )

    async def remove(self, path: str) -> None:
        # A removal has no document left to read, so the path is the only
        # thing that can name what went away — which is the other half of why
        # the path carries the identity rather than the label.
        kind, uid = _ref_from(path)
        if not self._resources.converges(kind):
            return
        if await self._find(uid) is None:
            # Already gone here — two machines deleting the same resource is
            # agreement, not a failure. This is also what a tree written by the
            # previous bundle layout degrades to: its paths spell names, no
            # name is a uid this vault ever minted, and the deletions that
            # clear them out of the tree therefore match nothing and do
            # nothing.
            return
        await self._resources.delete(uid, self._actor)

    async def _find(self, uid: str) -> Resource | None:
        try:
            return await self._resources.get(uid)
        except ResourceNotFound:
            return None


class StateApplier:
    """``state/<area>/…`` — module-owned shared state.

    Dispatches to whichever provider claims the area. An area no provider
    claims is skipped rather than failed: it belongs to a module this build
    does not have, and refusing it every round would turn a version difference
    into a permanent error.

    A state document is carried with the same ``${HOME}`` sentinel a resource
    document is (spec vault-sync ``## Determinism and path portability``), so
    it is expanded against this machine's home here, exactly as the resource
    applier does — one rule for every serialized document.
    """

    prefix = "state/"

    def __init__(
        self,
        providers: Sequence[SyncedStatePort],
        *,
        worktree: pathlib.Path,
        home: str | None = None,
    ) -> None:
        self._providers = {p.area: p for p in providers}
        self._worktree = worktree
        self._home = home

    async def upsert(self, path: str) -> None:
        provider, rel = self._route(path)
        if provider is None:
            return
        doc = await asyncio.to_thread(_read_yaml, self._worktree / path)
        if self._home:
            doc = expand_home(doc, self._home)
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


def _ref_from(path: str) -> tuple[str, str]:
    """Kind and uid, read out of ``resources/<kind>/<uid>.yaml``.

    The path alone, because the one caller is a removal and a removal has no
    document left to read.
    """
    parts = path.split("/")
    if len(parts) != 3:
        raise SyncSerializationError(f"{path} is not resources/<kind>/<uid>.yaml")
    return parts[1], parts[2].removesuffix(".yaml")


def _identity_from(doc: Mapping[str, object], path: str) -> tuple[str, str, str]:
    """Uid, kind and name for an upsert — read from the document, checked
    against the path.

    The document is the authority: it is the thing the exporter wrote and the
    thing git merged, and it is where the *name* lives at all. But the tree
    files it under its identity, so the two spellings have to agree, and a
    disagreement is refused rather than resolved. Picking a side would mean
    choosing between applying a document to a resource it does not claim to be
    and re-filing it under an identity it does not carry — and a hand-edited
    or half-copied tree is exactly the case where guessing costs the user a
    resource.

    A document with no ``uid`` at all lands here as the same refusal, and that
    is the right reading of it: it was written by a build on the previous
    bundle layout, and it names a resource this one cannot identify. The
    per-path failure is reported, the path is held so the next export does not
    publish it as a deletion, and the round carries on.
    """
    uid, kind, name = doc.get("uid"), doc.get("kind"), doc.get("name")
    if not (isinstance(uid, str) and uid):
        raise SyncSerializationError(f"{path} has no 'uid'")
    if not (isinstance(kind, str) and kind and isinstance(name, str) and name):
        raise SyncSerializationError(f"{path} has no 'kind'/'name'")
    path_kind, path_uid = _ref_from(path)
    if (path_kind, path_uid) != (kind, uid):
        raise SyncSerializationError(
            f"{path} is filed as {path_kind}/{path_uid} but the document says {kind}/{uid}"
        )
    return uid, kind, name
