"""Putting one document's change into the vault (spec vault-sync step 5 of
"Run the seven round steps in order").

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
import logging
import pathlib
from collections.abc import Collection, Sequence

from coffer.application.sync.appliers_read import read_yaml
from coffer.application.sync.ports import CredentialSyncPort, SyncedStatePort
from coffer.domain.sync.errors import SyncSerializationError
from coffer.domain.sync.fernet_time import is_fresher
from coffer.domain.sync.portability import expand_home

_logger = logging.getLogger(__name__)


class TreeApplier:
    """``knowledge/`` and ``skills/`` — files, mirrored one path at a time.

    The file trees are the vault's own storage, so applying is a copy and
    removal is an unlink. No index to rebuild: the knowledge layer is a
    directory (ADR knowledge-is-plain-files), which is most of why bidirectional
    convergence is affordable at all.

    ``excluded`` names bundle-relative directory prefixes this applier ignores outright,
    upsert and removal alike — the derived subtrees the exporter also refuses to publish
    (spec vault-sync "Withhold derived output in both halves"). The exporter's half is
    not enough on its own: it silences this machine, while a machine still running an
    older build keeps publishing `skills/coffer-guide/` and would otherwise overwrite a
    master folder this machine rendered for itself — the one direction an export-side
    rule cannot reach. Removal is ignored for the stronger reason: the folder here is
    written from the running build at every boot, so a deletion in the tree has no
    standing over it and obeying one would only unlink a manual that comes straight
    back.
    """

    def __init__(
        self,
        prefix: str,
        *,
        worktree: pathlib.Path,
        live_root: pathlib.Path,
        excluded: Collection[str] = (),
    ) -> None:
        self.prefix = prefix
        self._worktree = worktree
        self._live_root = live_root
        self._excluded = tuple(excluded)

    async def upsert(self, path: str) -> None:
        if self._ignored(path):
            return
        await asyncio.to_thread(self._copy_in, path)

    async def remove(self, path: str) -> None:
        if self._ignored(path):
            return
        await asyncio.to_thread(self._unlink, path)

    def _ignored(self, path: str) -> bool:
        """Whether this bundle path names derived output this machine owns.

        The prefixes carry their trailing ``/``, so ``skills/coffer-guide/``
        never swallows a user's own ``skills/coffer-guidelines/``.
        """
        return any(path.startswith(prefix) for prefix in self._excluded)

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


class StateApplier:
    """``state/<area>/…`` — module-owned shared state.

    Dispatches to whichever provider claims the area. An area no provider
    claims is skipped rather than failed: it belongs to a module this build
    does not have, and refusing it every round would turn a version difference
    into a permanent error.

    A state document is carried with the same ``${HOME}`` sentinel a resource
    document is (spec vault-sync "Store home paths against a sentinel"), so
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
        doc = await asyncio.to_thread(read_yaml, self._worktree / path)
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


async def locked_refs(credentials: CredentialSyncPort) -> tuple[str, ...]:
    """The refs this machine holds ciphertext for but cannot open, or none.

    Asked after a round's apply, so it must not be able to take the round down:
    the vault has already changed, and a failure escaping here (a busy database)
    would leave that change with no recorded run. It is a report, so a failure
    reports nothing and says so in the log (spec vault-sync "Report refs without
    a key as locked").
    """
    try:
        return tuple(await asyncio.to_thread(credentials.locked_refs))
    except Exception:
        _logger.warning("sync.locked_refs_failed", exc_info=True)
        return ()
