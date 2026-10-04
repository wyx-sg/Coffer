"""Reading and shaping the trees a round merges (spec vault-sync).

Three jobs, all over trees in the object store and none over the working
tree:

- settle **credential** conflicts by the ciphertexts' own encryption time —
  decidable without the key, and a person shown two opaque blobs could not
  choose (ADR secrets-cross-machines-only-as-ciphertext);
- find the **identity** conflicts git cannot see: one uid at two paths (a
  rename git failed to pair), and two resources of one kind with the same
  name but different uids (ADR identity-is-the-uid-inside-the-file; the user's
  rule for joins: stop and ask which to keep, or rename one);
- read the uid of every resource file, for the breaker's uid-counted losses.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from coffer.application.sync.round_ports import SyncGitPort
from coffer.domain.sync.stops import ConflictFile, ConflictReason
from coffer.domain.vault.document import DocumentInvalid, parse_resource
from coffer.domain.vault.fernet_time import is_fresher
from coffer.domain.vault.layout import (
    MACHINES,
    RESOURCES,
    SECRET,
    area_of,
    kind_of_resource_path,
)
from coffer.domain.vault.trees import ConflictEntry


@dataclass(frozen=True)
class ResourceIdentity:
    path: str
    uid: str | None
    kind: str
    name: str


class TreeReader:
    """Parses resource documents out of trees, caching by blob id."""

    def __init__(self, git: SyncGitPort) -> None:
        self._git = git
        self._by_blob: dict[str, ResourceIdentity | None] = {}

    def resources(self, tree: str) -> dict[str, ResourceIdentity]:
        """Every parseable resource document in ``tree``, by path."""
        files = {
            p: b for p, b in self._git.files(tree, RESOURCES).items() if kind_of_resource_path(p)
        }
        missing = [b for b in set(files.values()) if b not in self._by_blob]
        if missing:
            for blob, data in self._git.blobs(missing).items():
                try:
                    doc = parse_resource(data)
                    self._by_blob[blob] = ResourceIdentity("", doc.uid, doc.kind, doc.name)
                except DocumentInvalid:
                    self._by_blob[blob] = None
        out: dict[str, ResourceIdentity] = {}
        for path, blob in files.items():
            ident = self._by_blob.get(blob)
            if ident is not None:
                out[path] = ResourceIdentity(path, ident.uid, ident.kind, ident.name)
        return out

    def uids(self, tree: str) -> dict[str, str]:
        return {p: r.uid for p, r in self.resources(tree).items() if r.uid}

    def blob(self, tree: str, path: str) -> str | None:
        return self._git.files(tree, path).get(path)


def settle_machines(
    git: SyncGitPort, tree: str, tip: str, own: str, *, base: str | None = None
) -> str:
    """Each machine writes only its own descriptor (spec vault-sync "Write only
    this machine's descriptor"): in the merged tree every other machine's
    descriptor is the remote's, whatever this vault holds — a fresh vault that
    never had them must not publish their deletion.

    The one exception is a person retiring another machine here: a descriptor
    the base had, this vault deleted and the remote left as the base had it
    stays deleted, so the retirement reaches the remote. If that machine wrote
    its descriptor again meanwhile, it is back, and the remote's copy wins."""
    theirs = git.files(tip, MACHINES)
    merged = git.files(tree, MACHINES)
    before = git.files(base, MACHINES) if base else {}
    overrides: dict[str, str | None] = {}
    for path in set(theirs) | set(merged):
        if path == own or merged.get(path) == theirs.get(path):
            continue
        retired = path not in merged and path in before and theirs.get(path) == before[path]
        if not retired:
            overrides[path] = theirs.get(path)
    return git.build_tree(tree, overrides) if overrides else tree


def settle_secrets(
    git: SyncGitPort, tree: str, conflicts: Sequence[ConflictEntry]
) -> tuple[str, list[ConflictEntry]]:
    """Resolve every conflict under ``secret/`` by the fresher Fernet
    token (a deletion never beats a ciphertext); answer the tree and the
    conflicts that remain."""
    overrides: dict[str, str | None] = {}
    remaining: list[ConflictEntry] = []
    for c in conflicts:
        if c.path.startswith(MACHINES + "/"):
            continue  # settled by settle_machines
        if not c.path.startswith(SECRET + "/"):
            remaining.append(c)
            continue
        if c.ours and c.theirs:
            data = git.blobs([c.ours, c.theirs])
            ours, theirs = data.get(c.ours, b""), data.get(c.theirs, b"")
            overrides[c.path] = c.theirs if is_fresher(theirs.strip(), ours.strip()) else c.ours
        else:
            overrides[c.path] = c.ours or c.theirs
    if overrides:
        tree = git.build_tree(tree, overrides)
    return tree, remaining


def identity_conflicts(
    reader: TreeReader, merged: str, local: str, remote: str
) -> list[ConflictFile]:
    """The uid and name clashes in ``merged`` that neither side had alone."""
    after = reader.resources(merged)
    ours = reader.resources(local)
    out: list[ConflictFile] = []
    by_uid: dict[str, list[str]] = {}
    by_name: dict[tuple[str, str], list[str]] = {}
    for path, ident in after.items():
        if ident.uid:
            by_uid.setdefault(ident.uid, []).append(path)
        by_name.setdefault((ident.kind, ident.name), []).append(path)
    seen: set[str] = set()
    for uid, paths in by_uid.items():
        if len(paths) < 2:
            continue
        incumbent = [p for p in paths if ours.get(p) is not None and ours[p].uid == uid]
        for path in sorted(p for p in paths if p not in incumbent):
            seen.add(path)
            out.append(
                ConflictFile(
                    path=path,
                    area=area_of(path),
                    reason=ConflictReason.DUPLICATE_UID,
                    ours=None,
                    theirs=reader.blob(merged, path),
                    other_path=incumbent[0] if incumbent else None,
                )
            )
    for (_kind, _name), paths in by_name.items():
        uids = {after[p].uid for p in paths}
        if len(paths) < 2 or len(uids) < 2:
            continue
        mine = [p for p in paths if p in ours and ours[p].uid == after[p].uid]
        other = [p for p in paths if p not in mine and p not in seen]
        for path in sorted(other):
            out.append(
                ConflictFile(
                    path=path,
                    area=area_of(path),
                    reason=ConflictReason.SAME_NAME_DIFFERENT_UID,
                    ours=reader.blob(local, path),
                    theirs=reader.blob(remote, path) or reader.blob(merged, path),
                    other_path=mine[0] if mine else None,
                )
            )
    return out


def overrides_for(conflicts: Iterable[ConflictFile]) -> dict[str, str | None]:
    """The tree edits every answered conflict makes. A same-name conflict
    answered "mine" keeps only this machine's file; "theirs" keeps only the
    other's; "edited" puts the person's version at the conflicting path."""
    out: dict[str, str | None] = {}
    for c in conflicts:
        if c.reason is ConflictReason.SAME_NAME_DIFFERENT_UID and c.answer is not None:
            if c.answer.value == "mine":
                out[c.path] = c.ours
            elif c.answer.value == "theirs":
                out[c.path] = c.theirs
                if c.other_path:
                    out[c.other_path] = None
            else:
                out[c.path] = c.edited
            continue
        if c.reason is ConflictReason.DUPLICATE_UID and c.answer is not None:
            out[c.path] = (
                c.edited
                if c.answer.value == "edited"
                else (None if c.answer.value == "mine" else c.theirs)
            )
            if c.answer.value == "theirs" and c.other_path:
                out[c.other_path] = None
            continue
        out[c.path] = c.chosen_blob
    return out


def conflict_files(
    entries: Sequence[ConflictEntry], *, reason_for: Mapping[str, ConflictReason] | None = None
) -> list[ConflictFile]:
    """git's conflicted paths as the files a person answers."""
    out: list[ConflictFile] = []
    for e in entries:
        reason = (reason_for or {}).get(e.path) or (
            ConflictReason.BOTH_CHANGED
            if e.ours and e.theirs
            else ConflictReason.CHANGED_AND_DELETED
        )
        out.append(
            ConflictFile(
                path=e.path,
                area=area_of(e.path),
                reason=reason,
                ours=e.ours,
                theirs=e.theirs,
                base=e.base,
            )
        )
    return out


__all__ = [
    "ResourceIdentity",
    "TreeReader",
    "conflict_files",
    "identity_conflicts",
    "overrides_for",
    "settle_machines",
    "settle_secrets",
]
