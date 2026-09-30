"""What curation last settled, and which documents a person has changed since
(spec knowledge "Settle an item only after its pass completes"; ADR
every-vault-write-is-a-validated-commit-naming-its-writer: modification time
never decides).

``local/curation.json`` records, per document, the blob id the document had
when curation last settled it — after a pass over it, after a pass wrote it,
or when material was promoted into it — and when. It is machine-local state
(it can be rebuilt by letting curation look at everything once), so it is never
committed and never synced.

A document is **pending** when the blob it has at ``HEAD`` differs from the
settled one *and* the newest commit that touched it is not a ``curation`` or a
``sync`` write: a person's edit (``user`` through a surface, ``disk`` found on
disk) or an agent's is carried into the rest of the collection; Coffer's own
curation output and another machine's already-curated change are not. A
checkout, a backup restore or a clock change that only moves modification
times changes no blob, so it makes nothing pending.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from coffer.domain.vault.content_ids import blob_id
from coffer.domain.vault.writers import WRITER_CURATION, WRITER_SYNC
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.catalogue import is_markdown
from coffer.infrastructure.knowledge.history import KNOWLEDGE_HISTORY, KnowledgeHistory
from coffer.infrastructure.vault.home import local_root
from coffer.infrastructure.vault.json_store import JsonStore

#: The file under ``local/``.
STATE_FILENAME = "curation.json"
_DOCUMENTS = "documents"
#: Writers whose change to a document is not a person's edit to carry outward.
_NOT_AN_EDIT = frozenset({WRITER_CURATION, WRITER_SYNC})
#: How many commits one read of the log asks for while finding who last
#: touched each changed document.
_BATCH = 200

_STORE = JsonStore(lambda: local_root() / STATE_FILENAME)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def record(relpath: str, data: bytes, *, when: str | None = None) -> None:
    """Curation has settled ``relpath`` as ``data``."""

    def change(state: dict[str, Any]) -> None:
        state.setdefault(_DOCUMENTS, {})[relpath] = {"blob": blob_id(data), "at": when or _now()}

    _STORE.update(change)


def record_file(relpath: str, *, when: str | None = None) -> None:
    """Curation has settled ``relpath`` as it is on disk now."""
    target = paths.resolve(relpath)
    if target.is_file():
        record(relpath, target.read_bytes(), when=when)


def move(old: str, new: str) -> None:
    """A collection was renamed: its documents keep what curation settled."""
    old_prefix, new_prefix = f"{old}/", f"{new}/"

    def change(state: dict[str, Any]) -> None:
        docs = state.get(_DOCUMENTS, {})
        for key in [k for k in docs if k.startswith(old_prefix)]:
            docs[new_prefix + key[len(old_prefix) :]] = docs.pop(key)

    _STORE.update(change)


def curated_at(relpath: str, data: bytes) -> str:
    """When curation settled ``relpath`` as exactly ``data``; empty when it
    never did, or the document has changed since."""
    entry = _STORE.read().get(_DOCUMENTS, {}).get(relpath) or {}
    if entry.get("blob") != blob_id(data):
        return ""
    return str(entry.get("at") or "")


def _is_document(relpath: str, collection: str) -> bool:
    parts = relpath.split("/")
    if parts[0] != collection or len(parts) < 2 or any(p.startswith(".") for p in parts):
        return False
    if len(parts) == 2 and parts[1] == paths.README_NAME:
        return False
    return is_markdown(parts[-1])


def edited_documents(
    collection: str, *, history: KnowledgeHistory = KNOWLEDGE_HISTORY
) -> tuple[str, ...]:
    """Documents a person (or an agent) changed since curation last settled
    them, oldest change first.

    Edits still on disk are committed first as ``disk`` writes (an open
    operation's paths excepted), so a document edited in an editor a moment
    ago is judged by the same ``HEAD`` as everything else.
    """
    if not paths.collection_dir(collection).is_dir() or not history.available():
        return ()
    history.settle(collection)
    repo = history.writer().repo
    settled = _STORE.read().get(_DOCUMENTS, {})
    changed: set[str] = set()
    for vault_path, blob in repo.tree("HEAD", paths.vault_path(collection)).items():
        relpath = paths.from_vault_path(vault_path)
        if relpath is None or not _is_document(relpath, collection):
            continue
        if (settled.get(relpath) or {}).get("blob") != blob:
            changed.add(relpath)
    last: dict[str, tuple[float, str]] = {}
    skip = 0
    while changed - last.keys():
        batch = history.log(collection, limit=_BATCH, skip=skip)
        if not batch:
            break
        skip += len(batch)
        for change in batch:
            for doc in change.documents:
                if doc.path in changed and doc.path not in last:
                    last[doc.path] = (change.time.timestamp(), change.meta.writer)
    pending = sorted(
        (when, relpath) for relpath, (when, writer) in last.items() if writer not in _NOT_AN_EDIT
    )
    return tuple(relpath for _when, relpath in pending)


__all__ = [
    "STATE_FILENAME",
    "curated_at",
    "edited_documents",
    "move",
    "record",
    "record_file",
]
