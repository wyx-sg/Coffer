"""A kind's state documents in the vault: ``state/<area>/<owner name>.json``
(plan D13; spec vault-storage).

Some state belongs to a resource without being part of it — an MCP server's
capability switches, a channel's paired chats. It is the person's, so it is in
the vault and travels; it is not the resource's configuration, so it is a
document of its own, one per owner, named after the owner and carrying the
owner's uid inside (``server_uid``, ``channel_uid``). The uid is what the
document is found by; the file name only follows the owner's label, and the
resource store moves or deletes the document in the same commit when the
owner is renamed or deleted (:meth:`StateDocuments.follow`).

Reads are the documents at ``HEAD`` (plan D8), parsed once and refreshed when
a commit touches the area — and, for a path the writer holds
(``VaultWriter.held``: a join's differing file left as it is here until the
person chooses), the document on disk, which is the one in effect. Every
commit that reaches the writer's listeners — the daemon's own, a hand edit
the scanner settled, a sync round's checkout, a restore — refreshes the cache
the same way, and each owner whose document changed is announced to the
owner listeners (:meth:`StateDocuments.add_owner_listener`), which the
composition root points at the resource store's ``Changed`` hints.

Writes are read-modify-write through the vault's
one writer against ``HEAD``: every key the document already had and this
build does not write is kept, in place. A write that changes nothing makes no
commit.

:class:`StateDocument` is the one-file variant (``state/settings/internal-engine.json``).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from coffer.domain.resource import Resource
from coffer.domain.vault.content_ids import blob_id
from coffer.domain.vault.document import DocumentInvalid, decode, encode, merge_ordered
from coffer.domain.vault.formats import FORMAT_VERSION_KEY
from coffer.domain.vault.layout import DOCUMENT_SUFFIX, STATE, state_path
from coffer.domain.vault.writers import OP_DELETE, OP_UPDATE
from coffer.domain.vault.writes import CommitResult, Expect
from coffer.infrastructure.vault.actor_meta import commit_meta
from coffer.infrastructure.vault.home import vault_root
from coffer.infrastructure.vault.instance import vault_writer
from coffer.infrastructure.vault.writer import Transaction, VaultWriter

logger = logging.getLogger(__name__)

STATE_FORMAT_VERSION = 1


def _encode_over(original: Mapping[str, Any] | None, doc: Mapping[str, Any]) -> bytes:
    known = {FORMAT_VERSION_KEY: STATE_FORMAT_VERSION, **doc}
    return encode(merge_ordered(original, known, tuple(known)))


#: ``(path, document before, document after)`` of each path a commit changed.
Moved = list[tuple[str, dict[str, Any] | None, dict[str, Any] | None]]


class _HeadCache:
    """The parsed documents under one prefix at ``HEAD`` (held paths: disk)."""

    def __init__(self, writer: VaultWriter, prefix: str) -> None:
        self._writer = writer
        self._prefix = prefix
        self._lock = threading.RLock()
        self._docs: dict[str, tuple[str, dict[str, Any]]] = {}
        self._dirty = True
        self._listeners: list[Callable[[Moved], None]] = []
        writer.add_listener(self._on_commit)

    def add_listener(self, listener: Callable[[Moved], None]) -> None:
        self._listeners.append(listener)

    def _load(self, path: str) -> None:
        data = self._writer.read_disk(path)
        self._docs.pop(path, None)
        if data is None or not path.endswith(DOCUMENT_SUFFIX):
            return
        try:
            self._docs[path] = (blob_id(data), decode(data))
        except DocumentInvalid:
            logger.warning("vault.state_unreadable", extra={"path": path})

    def _on_commit(self, result: CommitResult) -> None:
        """Apply the commit's paths under the prefix from disk (``HEAD``'s
        bytes right after a commit, or a held path's effective bytes) instead
        of listing the tree again, then tell the listeners what moved."""
        mine = [p for p in result.paths if p.startswith(self._prefix)]
        if not mine:
            return
        with self._lock:
            if self._dirty:
                self._refresh()
                before: dict[str, dict[str, Any] | None] = {}
            else:
                before = {p: self._doc(p) for p in mine}
                for path in mine:
                    self._load(path)
            moved: Moved = [(p, before.get(p), self._doc(p)) for p in mine]
        for listener in list(self._listeners):
            try:
                listener(moved)
            except Exception:
                logger.warning("vault.state_listener_failed", exc_info=True)

    def _doc(self, path: str) -> dict[str, Any] | None:
        found = self._docs.get(path)
        return found[1] if found is not None else None

    def invalidate(self) -> None:
        with self._lock:
            self._dirty = True

    def docs(self) -> dict[str, dict[str, Any]]:
        """``{path: document}`` of every parseable document under the prefix."""
        with self._lock:
            if self._dirty:
                self._refresh()
            return {p: d for p, (_b, d) in self._docs.items()}

    def _refresh(self) -> None:
        self._dirty = False
        repo = self._writer.repo
        repo.ensure()
        tree = {
            p: b for p, b in repo.tree("HEAD", self._prefix).items() if p.endswith(DOCUMENT_SUFFIX)
        }
        wanted = sorted({b for p, b in tree.items() if self._docs.get(p, ("", {}))[0] != b})
        blobs = repo.read_blobs(wanted)
        out: dict[str, tuple[str, dict[str, Any]]] = {}
        for path, blob in tree.items():
            old = self._docs.get(path)
            if old is not None and old[0] == blob:
                out[path] = old
                continue
            try:
                out[path] = (blob, decode(blobs.get(blob, b"")))
            except DocumentInvalid:
                logger.warning("vault.state_unreadable", extra={"path": path})
        self._docs = out
        for path in self._writer.held():
            if path.startswith(self._prefix):
                self._load(path)


class StateDocuments:
    """The documents of one ``state/<area>/``, keyed by their owner's uid."""

    def __init__(self, area: str, owner_field: str, *, home: Path | None = None) -> None:
        self.area = area
        self.owner_field = owner_field
        self._writer = vault_writer(vault_root(home))
        self._cache = _HeadCache(self._writer, f"{STATE}/{area}/")
        self._owner_listeners: list[Callable[[str], None]] = []
        self._cache.add_listener(self._announce)

    def invalidate(self) -> None:
        self._cache.invalidate()

    def add_owner_listener(self, listener: Callable[[str], None]) -> None:
        """Call ``listener(owner_uid)`` for each owner whose document a
        commit changed, whoever made the commit."""
        self._owner_listeners.append(listener)

    def _announce(self, moved: Moved) -> None:
        owners: list[str] = []
        for _path, before, after in moved:
            for doc in (before, after):
                owner = doc.get(self.owner_field) if doc is not None else None
                if isinstance(owner, str) and owner and owner not in owners:
                    owners.append(owner)
        for owner in owners:
            for listener in list(self._owner_listeners):
                listener(owner)

    def _by_owner(self) -> dict[str, tuple[str, dict[str, Any]]]:
        out: dict[str, tuple[str, dict[str, Any]]] = {}
        for path, doc in sorted(self._cache.docs().items()):
            owner = doc.get(self.owner_field)
            if isinstance(owner, str) and owner and owner not in out:
                out[owner] = (path, doc)
        return out

    def all(self) -> dict[str, dict[str, Any]]:
        return {owner: doc for owner, (_p, doc) in self._by_owner().items()}

    def get(self, owner_uid: str) -> dict[str, Any] | None:
        found = self._by_owner().get(owner_uid)
        return found[1] if found else None

    def path_of(self, owner_uid: str) -> str | None:
        found = self._by_owner().get(owner_uid)
        return found[0] if found else None

    def _free_path(self, owner_uid: str, owner_name: str) -> str:
        taken = set(self._cache.docs())
        for label in (owner_name, f"{owner_name}-{owner_uid[:8]}", f"{owner_name}-{owner_uid}"):
            candidate = state_path(self.area, label)
            if candidate not in taken and self._writer.read_disk(candidate) is None:
                return candidate
        return state_path(self.area, owner_uid)

    def stage(
        self, txn: Transaction, owner_uid: str, owner_name: str, doc: Mapping[str, Any]
    ) -> None:
        """Write ``doc`` (the fields this build knows) inside ``txn``."""
        body = {self.owner_field: owner_uid, **doc}
        found = self._by_owner().get(owner_uid)
        if found is None:
            txn.write(
                self._free_path(owner_uid, owner_name), _encode_over(None, body), Expect.ABSENT
            )
        else:
            path, original = found
            txn.write(path, _encode_over(original, body), Expect.HEAD)

    def put(
        self,
        owner_uid: str,
        owner_name: str,
        doc: Mapping[str, Any],
        *,
        summary: str,
        actor: str | None = None,
    ) -> None:
        """Write the owner's document as one commit (none if nothing changed)."""
        with self._writer.begin(commit_meta(OP_UPDATE, summary, actor)) as txn:
            self.stage(txn, owner_uid, owner_name, doc)

    def remove(self, owner_uid: str, *, summary: str, actor: str | None = None) -> None:
        path = self.path_of(owner_uid)
        if path is None:
            return
        with self._writer.begin(commit_meta(OP_DELETE, summary, actor)) as txn:
            txn.delete(path, Expect.HEAD)

    def follow(self, txn: Transaction, owner: Resource, new_name: str | None) -> None:
        """The resource store's follower: move the owner's document to its new
        name, or delete it with the owner, inside the owner's own commit."""
        found = self._by_owner().get(owner.uid)
        if found is None:
            return
        path, original = found
        if new_name is None:
            txn.delete(path, Expect.HEAD)
            return
        target = state_path(self.area, new_name)
        if target == path:
            return
        if target in self._cache.docs() or self._writer.read_disk(target) is not None:
            target = state_path(self.area, f"{new_name}-{owner.uid[:8]}")
        txn.write(target, _encode_over(original, dict(original)), Expect.ABSENT)
        txn.delete(path, Expect.HEAD)


class StateDocument:
    """One fixed state document (``state/settings/internal-engine.json``)."""

    def __init__(self, area: str, name: str, *, home: Path | None = None) -> None:
        self.path = state_path(area, name)
        self._writer = vault_writer(vault_root(home))
        self._cache = _HeadCache(self._writer, self.path)

    def get(self) -> dict[str, Any] | None:
        return self._cache.docs().get(self.path)

    def put(self, doc: Mapping[str, Any], *, summary: str, actor: str | None = None) -> None:
        original = self.get()
        data = _encode_over(original, doc)
        expected = Expect.ABSENT if original is None else Expect.HEAD
        with self._writer.begin(commit_meta(OP_UPDATE, summary, actor)) as txn:
            txn.write(self.path, data, expected)

    def remove(self, *, summary: str, actor: str | None = None) -> None:
        if self.get() is None:
            return
        with self._writer.begin(commit_meta(OP_DELETE, summary, actor)) as txn:
            txn.delete(self.path, Expect.HEAD)


__all__ = ["STATE_FORMAT_VERSION", "StateDocument", "StateDocuments"]
