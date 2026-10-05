"""Resources as files: the ``ResourceRepo`` of the vault layout (spec
vault-storage; ADR identity-is-the-uid-inside-the-file).

Each resource is one JSON document, filed by its kind's storage class
(``Kind.storage``, refined per row by ``Kind.storage_row``):

- ``vault/resources/<kind>/<name>.json`` — written only through the vault's
  one writer, each change one commit naming its writer (the actor the service
  stated, ``coffer.application.resource_actor``); read at ``HEAD``;
- ``local/resources/<kind>/<name>.json`` and
  ``derived/resources/<kind>/<name>.json`` — written atomically, no history.

What the file does **not** hold: ``enabled`` and ``scope`` are reach, true of
this machine only, in ``local/reach.json`` (``reach_store``); ``updated_at``
is the file's modification time on this machine. ``set_enabled``
and ``update_scope`` therefore touch no file and make no commit.

Structured writes are read-modify-write under the vault's lock against what
``HEAD`` holds (``Expect.HEAD``; a new file ``Expect.ABSENT``), so a person's
unsettled edit to the same file is refused as ``VaultFileStale`` rather than
overwritten. A rename moves the file to ``<new name>.json`` in the
same commit, and a file name already used by an unrelated file falls back to
``<name>-<uid[:8]>.json``. Every other store that files a document after its
owner's name registers a *follower*: it is handed the open transaction on a
rename or delete, so the state document moves or goes in the same commit.

Every commit that reaches the writer's listeners without coming from this
store — a hand edit the scanner settled, a sync round's checkout, a restore —
refreshes the cache and is announced as ``Changed`` hints to the sink the
composition root sets (``resource_hints``), so the reconciler and the event
stream see it exactly as they see an API write. A state document's change is
announced for its owner through :meth:`FileResourceRepo.announce`.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coffer.domain.errors import ConfigValidationError, ResourceAlreadyExists, ResourceNotFound
from coffer.domain.reconcile import Changed
from coffer.domain.resource import Kind, Resource
from coffer.domain.scope import Scope
from coffer.domain.vault.document import ResourceDocument
from coffer.domain.vault.layout import StorageClass
from coffer.domain.vault.writers import OP_CREATE, OP_DELETE, OP_RENAME, OP_UPDATE
from coffer.domain.vault.writes import CommitResult, Expect
from coffer.infrastructure.vault.actor_meta import commit_meta
from coffer.infrastructure.vault.atomic import atomic_write, remove_file
from coffer.infrastructure.vault.home import vault_root
from coffer.infrastructure.vault.instance import vault_writer
from coffer.infrastructure.vault.reach_store import Reach, ReachStore, reach_path
from coffer.infrastructure.vault.resource_config import for_application, for_file
from coffer.infrastructure.vault.resource_files import Entry, ResourceFiles
from coffer.infrastructure.vault.resource_hints import ChangeAnnouncer, Known, Sink
from coffer.infrastructure.vault.writer import Transaction

logger = logging.getLogger(__name__)


def _parse_time(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


#: ``follower(txn, resource, new_name)``: the owner is being renamed to
#: ``new_name``, or deleted when it is ``None``. Called inside the one vault
#: transaction of that operation.
Follower = Callable[[Transaction, Resource, str | None], None]


class FileResourceRepo:
    """``ResourceRepo`` over resource files and this machine's reach."""

    def __init__(
        self,
        kinds: Mapping[str, Kind] | None = None,
        *,
        home: Path | None = None,
    ) -> None:
        # The registry is read at every use, not copied: the composition root
        # fills it while wiring the kinds, after this store exists.
        self._kinds: Mapping[str, Kind] = kinds if kinds is not None else {}
        self._base = home if home is not None else Path(os.environ.get("HOME", "~")).expanduser()
        self._writer = vault_writer(vault_root(self._base))
        self.files = ResourceFiles(self._writer, self._base)
        self._reach = ReachStore(reach_path(self._base))
        self._followers: list[Follower] = []
        self._hints = ChangeAnnouncer()
        # Registered after ``files``' own listener, so the cache is patched first.
        self._writer.add_listener(self._on_commit)

    # --- wiring -------------------------------------------------------------

    def add_follower(self, follower: Follower) -> None:
        self._followers.append(follower)

    def invalidate(self) -> None:
        self.files.invalidate()

    def set_change_sink(self, sink: Sink) -> None:
        """Announce the changes other writers make to ``sink`` (on the loop)."""
        self._hints.set_sink(sink)
        self._snapshot()

    def announce(self, uid: str) -> None:
        """A state document of ``uid`` changed: hint the owner, unless this
        store's own commit (a rename's follower) made the change."""
        if self._hints.owning() or not self._hints.active:
            return
        found = self._snapshot().get(uid)
        if found is not None:
            self._hints.emit(Changed(found.kind, found.uid, "upsert"))

    def _on_commit(self, result: CommitResult) -> None:
        mine = [p for p in result.paths if p.startswith("resources/")]
        if not mine or not self._hints.active or self._hints.owning():
            return
        before = self._hints.known()
        after = self._snapshot()
        self._hints.announce(mine, before, self._hints.known(), after)

    # --- reading --------------------------------------------------------------

    def _default_reach(self) -> Reach:
        return Reach(enabled=True, scope=None)

    def _snapshot(self) -> dict[str, Resource]:
        entries = self.files.by_uid()
        reach = self._reach.all()
        out: dict[str, Resource] = {}
        for uid, entry in entries.items():
            config = for_application(entry.doc.config)
            held = reach.get(uid) or self._default_reach()
            out[uid] = self._resource(entry, config, held)
        self._hints.remember(
            {
                e.path: Known(uid, e.doc.kind)
                for uid, e in entries.items()
                if e.storage is StorageClass.VAULT
            }
        )
        return out

    def _modified(self, entry: Entry) -> datetime | None:
        """When this machine last saw the file change: its modification time."""
        try:
            stamp = (self.files.root(entry.storage) / entry.path).stat().st_mtime
        except OSError:
            return None
        return datetime.fromtimestamp(stamp, tz=UTC)

    def _resource(self, entry: Entry, config: dict[str, Any], reach: Reach) -> Resource:
        doc = entry.doc
        modified = self._modified(entry)
        created = _parse_time(doc.created_at) or modified or datetime.now(tz=UTC)
        return Resource(
            uid=entry.uid,
            kind=doc.kind,
            name=doc.name,
            description=doc.description,
            config=config,
            # A kind with no switch is always on, whatever an old reach record says.
            enabled=reach.enabled or not getattr(self._kinds.get(doc.kind), "toggleable", True),
            created_at=created,
            updated_at=modified or created,
            scope=reach.scope,
            title=doc.title,
        )

    async def find(self, uid: str) -> Resource | None:
        return self._snapshot().get(uid)

    async def find_by_name(self, kind: str, name: str) -> Resource | None:
        for r in self._snapshot().values():
            if r.kind == kind and r.name == name:
                return r
        return None

    async def list(self, kind: str | None = None, enabled: bool | None = None) -> list[Resource]:
        rows = [
            r
            for r in self._snapshot().values()
            if (kind is None or r.kind == kind) and (enabled is None or r.enabled == enabled)
        ]
        # Ordered by (kind, name): a surface renders this as a list a person
        # clicks in, and the order must never depend on a write.
        return sorted(rows, key=lambda r: (r.kind, r.name))

    def name_of(self, uid: str) -> str | None:
        entry = self.files.by_uid().get(uid)
        return entry.doc.name if entry is not None else None

    def head_owners(self) -> dict[str, tuple[str, str, str]]:
        """``{uid: (path, kind, name)}`` of every vault resource at ``HEAD`` —
        what the validator compares a changed file against."""
        return {
            uid: (e.path, e.doc.kind, e.doc.name)
            for uid, e in self.files.by_uid().items()
            if e.storage is StorageClass.VAULT
        }

    # --- writing ----------------------------------------------------------------

    def _entry(self, uid: str) -> Entry:
        entry = self.files.by_uid().get(uid)
        if entry is None:
            raise ResourceNotFound(uid)
        if not entry.status.writable:
            raise ConfigValidationError(
                f"{entry.path} was written by a newer Coffer; it is read-only on this machine"
            )
        return entry

    def _storage_for(self, kind: str, config: dict[str, Any]) -> StorageClass:
        kind_def = self._kinds.get(kind)
        if kind_def is None:
            return StorageClass.VAULT
        if kind_def.storage_row is not None:
            return kind_def.storage_row(dict(config))
        return kind_def.storage

    def _put(
        self,
        txn: Transaction | None,
        entry_storage: StorageClass,
        path: str,
        data: bytes,
        expected: Expect,
    ) -> None:
        if entry_storage is StorageClass.VAULT:
            assert txn is not None
            txn.write(path, data, expected)
        else:
            atomic_write(self.files.root(entry_storage) / path, data)
            self.files.disk_changed(entry_storage, path)

    def _drop(self, txn: Transaction | None, storage: StorageClass, path: str) -> None:
        if storage is StorageClass.VAULT:
            assert txn is not None
            txn.delete(path, Expect.HEAD)
        else:
            root = self.files.root(storage)
            remove_file(root / path, stop_at=root)
            self.files.disk_changed(storage, path)

    def _commit(self, operation: str, summary: str, work: Callable[[Transaction], None]) -> None:
        with self._hints.own(), self._writer.begin(commit_meta(operation, summary)) as txn:
            work(txn)

    def _create(self, resource: Resource) -> None:
        current = self.files.by_uid()
        if resource.uid in current or any(
            e.doc.kind == resource.kind and e.doc.name == resource.name for e in current.values()
        ):
            raise ResourceAlreadyExists(resource.kind, resource.name)
        storage = self._storage_for(resource.kind, resource.config)
        doc = ResourceDocument(
            uid=resource.uid,
            kind=resource.kind,
            name=resource.name,
            description=resource.description,
            title=resource.title,
            config=for_file(resource.config),
            created_at=resource.created_at.astimezone(UTC).isoformat(),
        )
        path = self.files.free_path(storage, resource.kind, resource.name, resource.uid)
        summary = f"Registered {resource.kind} {resource.name}"
        if storage is StorageClass.VAULT:
            self._commit(OP_CREATE, summary, lambda t: t.write(path, doc.to_bytes(), Expect.ABSENT))
        else:
            self._put(None, storage, path, doc.to_bytes(), Expect.ABSENT)
        self._reach.put(resource.uid, Reach(enabled=resource.enabled, scope=resource.scope))

    async def create(self, resource: Resource) -> Resource:
        await asyncio.to_thread(self._create, resource)
        return await self._require(resource.uid)

    async def _require(self, uid: str) -> Resource:
        found = self._snapshot().get(uid)
        if found is None:
            raise ResourceNotFound(uid)
        return found

    def _rewrite(self, uid: str, summary: str, change: Callable[[Entry], ResourceDocument]) -> None:
        entry = self._entry(uid)
        doc = change(entry)
        data = doc.to_bytes()
        if entry.storage is StorageClass.VAULT:
            self._commit(OP_UPDATE, summary, lambda t: t.write(entry.path, data, Expect.HEAD))
        else:
            self._put(None, entry.storage, entry.path, data, Expect.HEAD)

    async def update_config(
        self, uid: str, config: dict[str, Any], description: str | None
    ) -> Resource:
        def change(entry: Entry) -> ResourceDocument:
            return entry.doc.replace(config=for_file(config), description=description)

        name = self.name_of(uid) or uid
        await asyncio.to_thread(self._rewrite, uid, f"Updated {name}", change)
        return await self._require(uid)

    async def set_title(self, uid: str, title: str | None) -> Resource:
        name = self.name_of(uid) or uid
        await asyncio.to_thread(
            self._rewrite, uid, f"Titled {name}", lambda e: e.doc.replace(title=title)
        )
        return await self._require(uid)

    def _set_reach(self, uid: str, change: Callable[[Reach], Reach]) -> None:
        entry = self.files.by_uid().get(uid)
        if entry is None:
            raise ResourceNotFound(uid)
        current = self._reach.get(uid) or self._default_reach()
        self._reach.put(uid, change(current))

    async def set_enabled(self, uid: str, enabled: bool) -> Resource:
        self._set_reach(uid, lambda r: Reach(enabled=enabled, scope=r.scope))
        return await self._require(uid)

    async def update_scope(self, uid: str, scope: Scope | None) -> Resource | None:
        if uid not in self.files.by_uid():
            return None
        normal = scope if scope is not None and scope.agents is not None else None
        self._set_reach(uid, lambda r: Reach(enabled=r.enabled, scope=normal))
        return await self._require(uid)

    def _ensure_writable(self, uid: str) -> None:
        entry = self._entry(uid)
        if entry.storage is StorageClass.VAULT:
            self._writer.compare(entry.path, self._writer.read_disk(entry.path), Expect.HEAD)

    async def ensure_writable(self, uid: str) -> None:
        await asyncio.to_thread(self._ensure_writable, uid)

    def _rename(self, uid: str, new_name: str) -> None:
        entry = self._entry(uid)
        kind = entry.doc.kind
        if any(
            e.doc.kind == kind and e.doc.name == new_name and e.uid != uid
            for e in self.files.by_uid().values()
        ):
            raise ResourceAlreadyExists(kind, new_name)
        before = self._snapshot()[uid]
        doc = entry.doc.replace(name=new_name)
        new_path = self.files.free_path(entry.storage, kind, new_name, uid)

        def work(txn: Transaction) -> None:
            if new_path != entry.path:
                self._put(txn, entry.storage, new_path, doc.to_bytes(), Expect.ABSENT)
                self._drop(txn, entry.storage, entry.path)
            else:
                self._put(txn, entry.storage, new_path, doc.to_bytes(), Expect.HEAD)
            for follower in self._followers:
                follower(txn, before, new_name)

        self._commit(OP_RENAME, f"Renamed {kind} {entry.doc.name} to {new_name}", work)

    async def rename(self, uid: str, new_name: str) -> Resource:
        await asyncio.to_thread(self._rename, uid, new_name)
        return await self._require(uid)

    def _delete(self, uid: str) -> None:
        entry = self.files.by_uid().get(uid)
        if entry is None:
            return  # idempotent
        before = self._snapshot()[uid]

        def work(txn: Transaction) -> None:
            self._drop(txn, entry.storage, entry.path)
            for follower in self._followers:
                follower(txn, before, None)

        self._commit(OP_DELETE, f"Deleted {entry.doc.kind} {entry.doc.name}", work)
        self._reach.remove(uid)

    async def delete(self, uid: str) -> None:
        await asyncio.to_thread(self._delete, uid)


__all__ = ["FileResourceRepo", "Follower"]
