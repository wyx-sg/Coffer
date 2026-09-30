"""Every accepted write to a collection, kept as one vault commit naming its
writer (spec knowledge "Keep every document's history and undo a pass as a
whole").

**Where the history lives.** Knowledge is inside the vault repository, at
``vault/knowledge/`` (ADR storage-is-five-classes-by-nature), so its history is
the vault's history of that directory (ADR
every-vault-write-is-a-validated-commit-naming-its-writer). This module is a
view over the process's one vault writer
(``coffer.infrastructure.vault.instance.vault_writer``): an operation's
:class:`Transaction` is a vault transaction whose touched paths are
``knowledge/<relpath>``, and log, show, diff and later are the vault
repository's, pathspec-limited to ``knowledge/`` with every path handed back
knowledge-root-relative — which is what every caller and API response speaks.

The vault's ``.git/info/exclude`` ignores every hidden entry under
``knowledge/`` except ``.inbox/``: the inbox is tracked, so a submission is a
commit and the text a pass consumed stays in history after the inbox file is
deleted.

**Who wrote what.** A Coffer operation opens a :class:`Transaction`, touches
the paths it writes, and commits exactly those. Anything else that changed
under ``knowledge/`` — a person's own editor, an agent's file tools — is
committed first, as a ``disk`` write (:meth:`KnowledgeHistory.settle`), so it
is never attributed to Coffer. A curation pass holds its transaction open for
minutes; the paths it has touched are *owned* by the vault writer meanwhile,
and a concurrent settle leaves them alone. A sync round's merge is a ``sync``
commit by construction, so nothing here marks sync's paths.

**Never in the way.** Without git every method is a no-op and
:meth:`available` is false: a write is never refused because it could not be
recorded.
"""

from __future__ import annotations

import logging
import os
import pathlib
from collections.abc import Callable

from coffer.domain.knowledge.history import Change, DocumentChange
from coffer.domain.vault.content_ids import fingerprint
from coffer.domain.vault.errors import VaultFileStale
from coffer.domain.vault.history import Commit, looks_like_a_version
from coffer.domain.vault.writers import CommitMeta
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.vault import git
from coffer.infrastructure.vault.atomic import atomic_write
from coffer.infrastructure.vault.instance import vault_writer
from coffer.infrastructure.vault.writer import Transaction as VaultTransaction
from coffer.infrastructure.vault.writer import VaultWriter

logger = logging.getLogger(__name__)

#: What recording failures look like; each is logged and the write stands.
_RECORDING_ERRORS = (git.VaultGitError, git.GitMissing, OSError)


class Transaction:
    """One Coffer operation's commit: the knowledge paths it touched,
    committed once as one vault commit."""

    def __init__(
        self,
        history: KnowledgeHistory | None,
        meta: CommitMeta,
        vault: VaultTransaction | None = None,
    ) -> None:
        self._history = history
        self._vault = vault
        self.meta = meta
        self.paths: list[str] = []
        #: Directories touched, re-expanded at commit time so a file the
        #: operation created inside one is part of its commit.
        self._dirs: list[str] = []
        self.version: str | None = None

    def touch(self, relpath: str) -> None:
        """Claim ``relpath`` — a document, or a whole directory — for this
        operation's commit. Touch before writing where possible: an owned path
        is never settled as someone else's edit."""
        if not relpath:
            return
        if relpath not in self.paths:
            self.paths.append(relpath)
        if self._vault is None or self._history is None:
            return
        if (paths.knowledge_root() / relpath).is_dir() and relpath not in self._dirs:
            self._dirs.append(relpath)
        for path in self._history.files_of(relpath):
            self._vault.touch(path)

    def write(self, relpath: str, data: bytes, expected: str) -> None:
        """Replace ``relpath``'s bytes if it still holds what the caller read
        (``expected`` is that read's fingerprint); raise ``VaultFileStale``
        otherwise. Compared under the vault's write lock when history is on."""
        if self._vault is not None:
            # Not ``touch`` first: the vault compares only a path this
            # transaction has not claimed yet, and claims it as it writes.
            if relpath not in self.paths:
                self.paths.append(relpath)
            self._vault.write(paths.vault_path(relpath), data, expected)
            return
        target = paths.resolve(relpath)
        current = target.read_bytes() if target.is_file() else None
        if current is None or fingerprint(current) != expected:
            raise VaultFileStale(paths.vault_path(relpath))
        atomic_write(target, data)

    def commit(self, meta: CommitMeta | None = None) -> str | None:
        """Commit what this operation touched; answer the commit, or ``None``
        when nothing changed. Idempotent: a second call commits nothing."""
        vault, history = self._vault, self._history
        self._vault = None
        if vault is None or history is None:
            return self.version
        try:
            for relpath in self._dirs:
                for path in history.files_of(relpath):
                    vault.touch(path)
            self.version = vault.commit(meta or self.meta)
        except _RECORDING_ERRORS:
            logger.warning("knowledge.history.commit_failed", exc_info=True)
        return self.version


class KnowledgeHistory:
    """The knowledge directory's view of the vault repository."""

    def __init__(self, writer: Callable[[], VaultWriter] = vault_writer) -> None:
        self._writer = writer

    # --- the repository ------------------------------------------------------

    def writer(self) -> VaultWriter:
        return self._writer()

    def available(self) -> bool:
        """Whether history is being recorded: git exists and the vault is a
        repository (it becomes one on first ask)."""
        if not git.git_available():
            return False
        try:
            self._writer().repo.ensure()
        except _RECORDING_ERRORS:
            logger.warning("knowledge.history.unavailable", exc_info=True)
            return False
        return True

    def files_of(self, relpath: str) -> list[str]:
        """Every vault path ``relpath`` stands for: itself when it names a
        file, else every file under it on disk or at ``HEAD``."""
        vp = paths.vault_path(relpath)
        target = paths.knowledge_root() / relpath
        found = dict.fromkeys(self._writer().repo.tree("HEAD", vp))
        if target.is_dir():
            vault = paths.knowledge_root().parent
            for root, _dirs, files in os.walk(target):
                for name in files:
                    found.setdefault((pathlib.Path(root) / name).relative_to(vault).as_posix())
        elif not found:
            found[vp] = None
        return list(found)

    # --- recording -----------------------------------------------------------

    def begin(self, meta: CommitMeta) -> Transaction:
        """Open one operation's commit, having committed what came before it."""
        if not self.available():
            return Transaction(None, meta)
        self.settle()
        return Transaction(self, meta, self._writer().begin(meta))

    def settle(self, relpath: str = "") -> None:
        """Commit what changed under ``knowledge/`` (or under ``relpath`` in it)
        outside any Coffer operation, as a ``disk`` write. Owned paths — an
        open operation's — are left for that operation's own commit."""
        if not self.available():
            return
        prefix = f"{paths.vault_path(relpath)}/"
        writer = self._writer()
        try:
            pending = [p for p in writer.pending() if p.startswith(prefix)]
            if pending:
                writer.settle(pending)
        except _RECORDING_ERRORS:
            logger.warning("knowledge.history.settle_failed", exc_info=True)

    # --- reading -------------------------------------------------------------

    def log(
        self,
        *relpaths: str,
        start: str | None = None,
        limit: int | None = None,
        skip: int = 0,
    ) -> list[Change]:
        """Commits newest first, from ``start`` (default ``HEAD``), that
        touched knowledge — ``relpaths`` in it, when given."""
        if not self.available():
            return []
        specs = [paths.vault_path(r) for r in relpaths] or [paths.VAULT_PREFIX]
        commits = self._writer().repo.log(*specs, start=start, limit=limit, skip=skip)
        return [_change(c) for c in commits]

    def change(self, version: str) -> Change | None:
        """One commit that touched knowledge, or ``None`` when there is none."""
        if not self.available() or not looks_like_a_version(version):
            return None
        commit = self._writer().repo.commit_of(version)
        if commit is None:
            return None
        found = _change(commit)
        return found if found.documents else None

    def show(self, version: str, relpath: str) -> bytes | None:
        """``relpath``'s bytes at ``version`` (``<id>^`` for its parent), or
        ``None`` where it did not exist."""
        if not self.available() or not looks_like_a_version(version.rstrip("^")):
            return None
        return self._writer().repo.read(version, paths.vault_path(relpath))

    def diff(self, version: str, relpath: str) -> str:
        """The unified diff ``version`` made to ``relpath``, its headers
        knowledge-root-relative (empty if none)."""
        if not self.available() or not looks_like_a_version(version):
            return ""
        done = git.run(
            self._writer().repo.root,
            "show",
            "--format=",
            "--patch",
            "--no-color",
            "--no-ext-diff",
            "--no-renames",
            f"--relative={paths.VAULT_PREFIX}/",
            version,
            "--",
            paths.vault_path(relpath),
            check=False,
            literal=True,
        )
        return git.text(done) if done.returncode == 0 else ""

    def later(self, version: str, relpath: str) -> str | None:
        """The newest commit after ``version`` that touched ``relpath``."""
        if not self.available() or not looks_like_a_version(version):
            return None
        return self._writer().repo.later(version, paths.vault_path(relpath))


def _change(commit: Commit) -> Change:
    documents = tuple(
        DocumentChange(path=rel, status=pc.status, added=pc.added, removed=pc.removed)
        for pc in commit.paths
        if (rel := paths.from_vault_path(pc.path)) is not None
    )
    return Change(version=commit.version, time=commit.time, meta=commit.meta, documents=documents)


#: The one history the daemon shares. It holds no state of its own — the lock
#: and the owned paths are the vault writer's, looked up by the vault root that
#: follows ``HOME`` — so every writer in the process consults the same one.
KNOWLEDGE_HISTORY = KnowledgeHistory()

__all__ = ["KNOWLEDGE_HISTORY", "KnowledgeHistory", "Transaction"]
