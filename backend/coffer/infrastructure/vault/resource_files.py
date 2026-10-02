"""Reading resource files of every storage class (spec vault-storage
"Identify a resource by the uid inside its file").

A resource is a JSON document at ``resources/<kind>/<name>.json`` under the
directory of its class: ``vault/`` (committed), ``local/`` (agents: this
machine only) or ``derived/`` (memory partitions and Coffer's own skill:
rebuilt). Nothing keys on the path — the uid inside the file is the identity —
so this module indexes whatever it finds by uid.

**The vault is read at ``HEAD``, never from the working tree**:
the effective version of a vault resource is the committed one, so a hand
edit that validation refused stays on disk, uncommitted and flagged, while
every reader keeps the last valid version. The tree is listed with one
``ls-tree`` and only blobs not already parsed are read (one ``cat-file
--batch``), so a refresh after a commit costs two processes, not one per file.
After a commit through the writer the cache is patched from the committed
paths themselves (their bytes on disk are ``HEAD``'s), so a write costs no
extra read; a full refresh is due only after :meth:`ResourceFiles.invalidate`
(a checkout that did not go through the writer).

The one exception is a path the writer *holds* (``VaultWriter.held``): a
join's file that differs, deliberately left different from ``HEAD`` until the
person chooses. Its effective version is the one on disk — that is what this
machine is running on — so a refresh reads held paths from the working tree.

``local/`` and ``derived/`` have no history: only the daemon writes them, and
they are read from disk.

A file at ``HEAD`` that does not parse, carries no uid yet (the daemon commit
minting one follows the person's), or was written by a newer Coffer in a
format this build cannot read is skipped and logged; validation keeps such a
file out of ``HEAD`` in the first place, so this is only what a hand ``git
commit`` in the vault can leave.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from coffer.domain.vault.content_ids import blob_id
from coffer.domain.vault.document import DocumentInvalid, ResourceDocument, parse_resource
from coffer.domain.vault.formats import FormatSpec, FormatStatus, read
from coffer.domain.vault.layout import DOCUMENT_SUFFIX, RESOURCES, StorageClass, resource_path
from coffer.domain.vault.writes import CommitResult
from coffer.infrastructure.vault.home import derived_root, local_root, vault_root
from coffer.infrastructure.vault.writer import VaultWriter

logger = logging.getLogger(__name__)

#: Every kind's resource document is at format 1 today; a kind that changes
#: its document's shape gets its own spec and upgrade chain here.
RESOURCE_FORMAT = FormatSpec(current=1)

#: The order a uid claimed in two classes is resolved in (a hand copy between
#: class directories): the vault's copy wins.
_CLASS_ORDER = (StorageClass.VAULT, StorageClass.LOCAL, StorageClass.DERIVED)


@dataclass(frozen=True)
class Entry:
    """One resource file as read: its class, its path inside that class's
    directory, the blob id of its bytes, and the parsed document."""

    storage: StorageClass
    path: str
    blob: str
    doc: ResourceDocument
    status: FormatStatus = FormatStatus.CURRENT

    @property
    def uid(self) -> str:
        assert self.doc.uid is not None
        return self.doc.uid


def _is_resource_path(path: str) -> bool:
    """``resources/<kind>/<name>.json`` — nothing deeper, nothing else."""
    return (
        path.startswith(f"{RESOURCES}/") and path.endswith(DOCUMENT_SUFFIX) and path.count("/") == 2
    )


def class_root(storage: StorageClass, base: Path | None) -> Path:
    if storage is StorageClass.VAULT:
        return vault_root(base)
    if storage is StorageClass.LOCAL:
        return local_root(base)
    if storage is StorageClass.DERIVED:
        return derived_root(base)
    raise ValueError(f"resources are not stored in {storage}")


def _parse(storage: StorageClass, path: str, data: bytes) -> Entry | None:
    try:
        doc = parse_resource(data)
    except DocumentInvalid as exc:
        logger.warning("vault.resource_unreadable", extra={"path": path, "reason": str(exc)})
        return None
    if doc.uid is None:
        return None
    try:
        status = read(doc.raw, RESOURCE_FORMAT).status
    except ValueError:
        return None
    if status is FormatStatus.NEWER_UNREADABLE:
        logger.warning("vault.resource_newer_format", extra={"path": path})
        return None
    return Entry(storage=storage, path=path, blob=blob_id(data), doc=doc, status=status)


class ResourceFiles:
    """The parsed resource files of one home, cached and refreshed on demand."""

    def __init__(self, writer: VaultWriter, base: Path | None) -> None:
        self._writer = writer
        self._base = base
        self._lock = threading.RLock()
        self._vault: dict[str, Entry] = {}
        self._others: dict[StorageClass, dict[str, Entry]] = {}
        self._by_uid: dict[str, Entry] = {}
        self._dirty = True
        writer.add_listener(self._on_commit)

    def _on_commit(self, result: CommitResult) -> None:
        """Apply a commit's resource paths to the cache without asking git:
        right after a commit, each path's bytes on disk are what ``HEAD``
        holds (or it is gone)."""
        mine = [p for p in result.paths if p.startswith(f"{RESOURCES}/")]
        if not mine:
            return
        with self._lock:
            if self._dirty:
                return
            for path in mine:
                data = self._writer.read_disk(path)
                entry = _parse(StorageClass.VAULT, path, data) if data is not None else None
                if entry is None or not _is_resource_path(path):
                    self._vault.pop(path, None)
                else:
                    self._vault[path] = entry
            self._index()

    def invalidate(self) -> None:
        """Re-read on the next access (a commit, a checkout by sync)."""
        with self._lock:
            self._dirty = True

    def root(self, storage: StorageClass) -> Path:
        return class_root(storage, self._base)

    def by_uid(self) -> dict[str, Entry]:
        with self._lock:
            if self._dirty:
                self._refresh()
            return dict(self._by_uid)

    def head_paths(self) -> dict[str, str]:
        """``{path: blob}`` of every vault resource file at ``HEAD``."""
        with self._lock:
            if self._dirty:
                self._refresh()
            return {p: e.blob for p, e in self._vault.items()}

    def free_path(self, storage: StorageClass, kind: str, name: str, uid: str) -> str:
        """Where a resource named ``name`` is filed: ``<name>.json``, unless an
        unrelated file already has that name."""
        held = {e.path: e.uid for e in self.by_uid().values() if e.storage is storage}
        taken = set(held)
        if storage is StorageClass.VAULT:
            taken |= set(self.head_paths())
        root = self.root(storage)
        for candidate in (resource_path(kind, name), resource_path(kind, f"{name}-{uid[:8]}")):
            owner = held.get(candidate)
            if owner == uid or (candidate not in taken and not (root / candidate).exists()):
                return candidate
        return resource_path(kind, f"{name}-{uid}")

    def _refresh(self) -> None:
        self._dirty = False
        self._vault = self._load_vault()
        for storage in (StorageClass.LOCAL, StorageClass.DERIVED):
            self._others[storage] = self._load_disk(storage)
        self._index()

    def disk_changed(self, storage: StorageClass, path: str) -> None:
        """A ``local/`` or ``derived/`` file this store just wrote or removed."""
        with self._lock:
            if self._dirty:
                return
            file = self.root(storage) / path
            data = file.read_bytes() if file.is_file() else None
            entry = _parse(storage, path, data) if data is not None else None
            if entry is None:
                self._others[storage].pop(path, None)
            else:
                self._others[storage][path] = entry
            self._index()

    def _index(self) -> None:
        by_uid: dict[str, Entry] = {}
        for storage in _CLASS_ORDER:
            source = self._vault if storage is StorageClass.VAULT else self._others[storage]
            for path in sorted(source):
                entry = source[path]
                held = by_uid.get(entry.uid)
                if held is not None:
                    logger.warning(
                        "vault.resource_uid_claimed_twice",
                        extra={"uid": entry.uid, "kept": held.path, "ignored": path},
                    )
                    continue
                by_uid[entry.uid] = entry
        self._by_uid = by_uid

    def _load_vault(self) -> dict[str, Entry]:
        repo = self._writer.repo
        repo.ensure()
        tree = {p: b for p, b in repo.tree("HEAD", f"{RESOURCES}/").items() if _is_resource_path(p)}
        wanted = sorted(
            {
                b
                for p, b in tree.items()
                if self._vault.get(p, None) is None or self._vault[p].blob != b
            }
        )
        blobs = repo.read_blobs(wanted)
        out: dict[str, Entry] = {}
        for path, blob in tree.items():
            old = self._vault.get(path)
            if old is not None and old.blob == blob:
                out[path] = old
                continue
            data = blobs.get(blob)
            entry = _parse(StorageClass.VAULT, path, data) if data is not None else None
            if entry is not None:
                out[path] = entry
        for path in self._writer.held():
            if not _is_resource_path(path):
                continue
            data = self._writer.read_disk(path)
            held = _parse(StorageClass.VAULT, path, data) if data is not None else None
            if held is None:
                out.pop(path, None)
            else:
                out[path] = held
        return out

    def _load_disk(self, storage: StorageClass) -> dict[str, Entry]:
        root = self.root(storage)
        out: dict[str, Entry] = {}
        base = root / RESOURCES
        if not base.is_dir():
            return out
        for file in sorted(base.glob(f"*/*{DOCUMENT_SUFFIX}")):
            if not file.is_file() or file.name.startswith("."):
                continue
            path = file.relative_to(root).as_posix()
            try:
                data = file.read_bytes()
            except OSError:
                continue
            entry = _parse(storage, path, data)
            if entry is not None:
                out[path] = entry
        return out


__all__ = ["RESOURCE_FORMAT", "Entry", "ResourceFiles", "class_root"]
