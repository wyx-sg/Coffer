"""Every accepted write to a collection, kept as one git commit naming its
writer (spec knowledge "Keep every document's history and undo a pass as a
whole").

**Where the history lives.** ADR
every-vault-write-is-a-validated-commit-naming-its-writer makes the vault one
git repository; until that lands, the knowledge root keeps a repository of its
own at ``<knowledge root>/.git``. It is shaped to fold into the vault's: the
same trailers (``history_git.TRAILERS``), one commit per operation, and paths
relative to the knowledge root, so the fold is a history import under
``knowledge/`` rather than a translation. It stays out of everything else by
construction — every knowledge listing skips dot-prefixed entries, the sync
mirror skips ``.git`` directories, and git will not accept a ``.git`` path from
a remote.

``.git/info/exclude`` ignores every dot-prefixed entry except ``.inbox/``: the
inbox is tracked, so a submission is a commit and the text a pass consumed stays
in history after the inbox file is deleted.

**Who wrote what.** A Coffer operation opens a :class:`Transaction`, touches
the paths it writes, and commits exactly those. Anything else that changed in
the tree — a person's own editor, an agent's file tools — is committed first,
as an edit on disk (:meth:`KnowledgeHistory.settle`), so it is never counted as
Coffer's. A curation pass holds its transaction open for minutes; the paths it
has touched are *owned* meanwhile, and a concurrent settle leaves them alone.
Paths vault sync applied are marked (:meth:`mark_sync`) and committed as
``sync`` before any disk edit is.

**Never in the way.** Without git — or with a knowledge root that does not
exist yet — every method is a no-op and :meth:`available` is false: a write is
never refused because it could not be recorded.
"""

from __future__ import annotations

import logging
import pathlib
import threading
from collections import Counter
from collections.abc import Callable, Iterable

from coffer.domain.knowledge.history import (
    OP_BASELINE,
    OP_EDIT,
    OP_SYNC,
    WRITER_DISK,
    WRITER_SYNC,
    Change,
    ChangeMeta,
)
from coffer.infrastructure.knowledge import paths
from coffer.infrastructure.knowledge.history_git import (
    LOG_FORMAT,
    GitCommandError,
    git_available,
    message,
    parse_log,
    run,
)

logger = logging.getLogger(__name__)

#: Ignore every hidden entry but the inbox. ``.git`` itself is never tracked.
_EXCLUDE = "# Written by Coffer: hidden entries are not knowledge, except the inbox.\n.*\n!.inbox\n"


class Transaction:
    """One Coffer operation's commit: the paths it touched, committed once."""

    def __init__(self, history: KnowledgeHistory | None, meta: ChangeMeta) -> None:
        self._history = history
        self.meta = meta
        self.paths: list[str] = []
        self.version: str | None = None

    def touch(self, relpath: str) -> None:
        """Claim ``relpath`` for this operation's commit."""
        if relpath and relpath not in self.paths:
            self.paths.append(relpath)
            if self._history is not None:
                self._history.own(relpath)

    def commit(self, meta: ChangeMeta | None = None) -> str | None:
        """Commit what this operation touched; answer the commit, or ``None``
        when nothing changed. Idempotent: a second call commits nothing."""
        if self._history is None:
            return None
        history, self._history = self._history, None
        self.version = history.finish(self.paths, meta or self.meta)
        return self.version


class KnowledgeHistory:
    """The knowledge root's history repository."""

    def __init__(self, root: Callable[[], pathlib.Path] = paths.knowledge_root) -> None:
        self._root = root
        self._lock = threading.RLock()
        self._owned: Counter[str] = Counter()
        self._sync_marks: set[str] = set()
        self._ready: set[str] = set()

    # --- the repository ------------------------------------------------------

    def root(self) -> pathlib.Path:
        return self._root()

    def available(self) -> bool:
        """Whether history is being recorded here: git exists and the
        repository could be created (it is, on first ask)."""
        return self._ensure()

    def _ensure(self) -> bool:
        root = self._root()
        key = str(root)
        if key in self._ready and (root / ".git").is_dir():
            return True
        if not git_available() or not root.is_dir():
            return False
        with self._lock:
            try:
                if not (root / ".git").is_dir():
                    run(root, "init", "-q")
                exclude = root / ".git" / "info" / "exclude"
                exclude.parent.mkdir(parents=True, exist_ok=True)
                if not exclude.is_file() or exclude.read_text(encoding="utf-8") != _EXCLUDE:
                    exclude.write_text(_EXCLUDE, encoding="utf-8")
                self._ready.add(key)
                if run(root, "rev-parse", "--verify", "-q", "HEAD", check=False).returncode:
                    # History starts here: whatever the tree already held is
                    # one baseline commit, so a first change has a "before".
                    self._commit_all(
                        ChangeMeta(
                            writer=WRITER_DISK,
                            operation=OP_BASELINE,
                            summary="History starts here",
                        )
                    )
            except (GitCommandError, OSError):
                logger.warning("knowledge.history.unavailable", exc_info=True)
                self._ready.discard(key)
                return False
        return True

    # --- recording -----------------------------------------------------------

    def begin(self, meta: ChangeMeta) -> Transaction:
        """Open one operation's commit, having committed what came before it."""
        if not self._ensure():
            return Transaction(None, meta)
        self.settle()
        return Transaction(self, meta)

    def own(self, relpath: str) -> None:
        with self._lock:
            self._owned[relpath] += 1

    def finish(self, relpaths: Iterable[str], meta: ChangeMeta) -> str | None:
        """Commit ``relpaths`` alone and release them."""
        touched = list(dict.fromkeys(relpaths))
        root = self._root()
        with self._lock:
            try:
                if not touched or not self._ensure():
                    return None
                self._stage(root, touched)
                return self._commit_staged(root, meta)
            except (GitCommandError, OSError):
                logger.warning("knowledge.history.commit_failed", exc_info=True)
                return None
            finally:
                for path in touched:
                    self._owned[path] -= 1
                    if self._owned[path] <= 0:
                        del self._owned[path]

    def mark_sync(self, relpath: str) -> None:
        """Vault sync applied ``relpath``: the next commit names sync."""
        with self._lock:
            self._sync_marks.add(relpath)

    def settle(self) -> None:
        """Commit what changed outside any Coffer operation: sync's paths as
        ``sync``, then everything else no open operation owns as an edit on
        disk."""
        if not self._ensure():
            return
        root = self._root()
        with self._lock:
            try:
                marks, self._sync_marks = sorted(self._sync_marks), set()
                if marks:
                    self._stage(root, marks)
                    self._commit_staged(
                        root,
                        ChangeMeta(
                            writer=WRITER_SYNC,
                            operation=OP_SYNC,
                            summary="Applied from another machine",
                        ),
                    )
                self._commit_all(
                    ChangeMeta(writer=WRITER_DISK, operation=OP_EDIT, summary="Edited on disk"),
                    leave=sorted(self._owned),
                )
            except (GitCommandError, OSError):
                logger.warning("knowledge.history.settle_failed", exc_info=True)

    def _stage(self, root: pathlib.Path, relpaths: Iterable[str]) -> None:
        for relpath in relpaths:
            if (root / relpath).exists():
                run(root, "add", "-A", "--", relpath, literal=True)
            else:
                run(
                    root,
                    "rm",
                    "-r",
                    "-q",
                    "--cached",
                    "--ignore-unmatch",
                    "--",
                    relpath,
                    literal=True,
                )

    def _commit_all(self, meta: ChangeMeta, *, leave: Iterable[str] = ()) -> str | None:
        root = self._root()
        if not run(root, "status", "--porcelain", "--untracked-files=all").stdout.strip():
            return None  # the usual case, and one process rather than three
        run(root, "add", "-A")
        for relpath in leave:
            # An open operation's path is its own commit's, not this one's.
            run(root, "reset", "-q", "--", relpath, check=False, literal=True)
        return self._commit_staged(root, meta)

    def _commit_staged(self, root: pathlib.Path, meta: ChangeMeta) -> str | None:
        if run(root, "diff", "--cached", "--quiet", check=False).returncode == 0:
            return None
        run(root, "commit", "-q", "--no-verify", "-F", "-", stdin=message(meta), writer=meta.writer)
        return run(root, "rev-parse", "HEAD").stdout.decode().strip()

    # --- reading -------------------------------------------------------------

    def log(
        self,
        *pathspecs: str,
        start: str | None = None,
        limit: int | None = None,
        skip: int = 0,
    ) -> list[Change]:
        """Commits newest first, from ``start`` (default ``HEAD``), touching
        ``pathspecs`` when given."""
        if not self._ensure():
            return []
        root = self._root()
        args = ["log", LOG_FORMAT, "--raw", "--numstat", "--no-renames", "--no-abbrev"]
        if limit is not None:
            args.append(f"-n{limit}")
        if skip:
            args.append(f"--skip={skip}")
        args.append(start or "HEAD")
        if pathspecs:
            args += ["--", *pathspecs]
        done = run(root, *args, check=False, literal=True)
        if done.returncode != 0:
            return []
        return parse_log(done.stdout)

    def change(self, version: str) -> Change | None:
        """One commit, or ``None`` when the history holds no such commit."""
        if not self._ensure() or not _looks_like_a_version(version):
            return None
        found = self.log(start=version, limit=1)
        return found[0] if found and found[0].version.startswith(version) else None

    def show(self, version: str, relpath: str) -> bytes | None:
        """``relpath``'s bytes at ``version``, or ``None`` where it did not exist."""
        if not self._ensure() or not _looks_like_a_version(version.rstrip("^")):
            return None
        done = run(self._root(), "show", f"{version}:{relpath}", check=False)
        return done.stdout if done.returncode == 0 else None

    def diff(self, version: str, relpath: str) -> str:
        """The unified diff ``version`` made to ``relpath`` (empty if none)."""
        if not self._ensure() or not _looks_like_a_version(version):
            return ""
        done = run(
            self._root(),
            "show",
            "--format=",
            "--patch",
            "--no-color",
            "--no-ext-diff",
            "--no-renames",
            version,
            "--",
            relpath,
            check=False,
            literal=True,
        )
        return done.stdout.decode("utf-8", "replace") if done.returncode == 0 else ""

    def later(self, version: str, relpath: str) -> str | None:
        """The newest commit after ``version`` that touched ``relpath``."""
        if not self._ensure():
            return None
        done = run(
            self._root(),
            "log",
            "--format=%H",
            "-n1",
            f"{version}..HEAD",
            "--",
            relpath,
            check=False,
            literal=True,
        )
        found = done.stdout.decode().strip()
        return found or None


def _looks_like_a_version(version: str) -> bool:
    """A commit id, and nothing git would read as an option or a range."""
    return 4 <= len(version) <= 64 and all(c in "0123456789abcdef" for c in version)


#: The one history the daemon shares: the lock and the owned paths only mean
#: something if every writer in the process consults the same instance.
KNOWLEDGE_HISTORY = KnowledgeHistory()

__all__ = ["KNOWLEDGE_HISTORY", "KnowledgeHistory", "Transaction"]
