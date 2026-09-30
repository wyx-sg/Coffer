"""The vault repository: reading it, and the low-level staging a writer uses.

The vault is a git repository from the moment it exists, whether or not a sync
remote is configured (ADR every-vault-write-is-a-validated-commit-naming-its-writer);
this class makes it one on first use and answers what git knows — the tree at
a commit, a blob, what differs from ``HEAD``, and the history of any path.

Nothing here decides *whether* a change may be committed; that is the writer's
job. ``stage`` and ``commit_staged`` are the two primitives it calls.

``.git/info/exclude`` — never a tracked ``.gitignore`` another machine could
change — keeps out editor and OS litter, hidden entries in knowledge (except
the inbox), and ``credentials/`` unless this vault carries credentials.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from coffer.domain.vault.history import Commit, looks_like_a_version
from coffer.domain.vault.layout import CREDENTIALS, MANIFEST, MANIFEST_SCHEMA_VERSION
from coffer.domain.vault.writers import OP_BASELINE, WRITER_DAEMON, CommitMeta, message
from coffer.infrastructure.vault import git
from coffer.infrastructure.vault.atomic import atomic_write
from coffer.infrastructure.vault.log_parse import LOG_FORMAT, parse_log, parse_ls_tree, parse_status

logger = logging.getLogger(__name__)

_EXCLUDE_BASE = """# Written by Coffer. Never synced: this file is inside .git.
.DS_Store
.*.tmp
.*.swp
*~
.#*
__pycache__/
*.py[co]
/knowledge/**/.*
!/knowledge/**/.inbox
"""
_EXCLUDE_CREDENTIALS = f"/{CREDENTIALS}/\n"


class VaultRepository:
    """The git repository at the vault root."""

    def __init__(self, root: Path | Callable[[], Path]) -> None:
        self._root = root if callable(root) else (lambda: root)
        self._lock = threading.RLock()
        self._ready: set[str] = set()
        self._carry_credentials = False

    # --- the repository ---------------------------------------------------

    @property
    def root(self) -> Path:
        return self._root()

    def exists(self) -> bool:
        return (self.root / ".git").is_dir()

    def ensure(self) -> None:
        """Make the vault a repository with its exclude file and a first
        commit. Raises ``GitMissing`` when git is not installed."""
        root = self.root
        key = str(root)
        if key in self._ready and (root / ".git").is_dir():
            return
        with self._lock:
            if not git.git_available():
                raise git.GitMissing()
            root.mkdir(parents=True, exist_ok=True)
            if not (root / ".git").is_dir():
                git.run(root, "init", "-q", "-b", "main")
            self._write_exclude(root)
            if not (root / MANIFEST).exists():
                atomic_write(root / MANIFEST, _manifest_bytes())
            if self.head() is None:
                git.run(root, "add", "-A")
                git.run(
                    root,
                    "commit",
                    "-q",
                    "--allow-empty",
                    "--no-verify",
                    "-F",
                    "-",
                    stdin=message(
                        CommitMeta(
                            writer=WRITER_DAEMON,
                            operation=OP_BASELINE,
                            summary="History starts here",
                        )
                    ).encode(),
                    writer=WRITER_DAEMON,
                )
            self._ready.add(key)

    def set_carry_credentials(self, carry: bool) -> None:
        """Whether ``credentials/`` is committed (only when the remote carries
        credentials; ADR credentials-across-machines)."""
        with self._lock:
            self._carry_credentials = carry
            if self.exists():
                self._write_exclude(self.root)

    @property
    def carries_credentials(self) -> bool:
        return self._carry_credentials

    def _write_exclude(self, root: Path) -> None:
        wanted = _EXCLUDE_BASE + ("" if self._carry_credentials else _EXCLUDE_CREDENTIALS)
        path = root / ".git" / "info" / "exclude"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.is_file() or path.read_text(encoding="utf-8") != wanted:
            path.write_text(wanted, encoding="utf-8")

    def run(self, *args: str, **kwargs: object) -> object:
        """Escape hatch for a caller in this package that needs a command
        not wrapped below (sync's merge-tree, read-tree, fetch, push)."""
        return git.run(self.root, *args, **kwargs)  # type: ignore[arg-type]

    # --- reading ------------------------------------------------------------

    def head(self) -> str | None:
        done = git.run(self.root, "rev-parse", "--verify", "-q", "HEAD^{commit}", check=False)
        sha = git.text(done).strip()
        return sha if done.returncode == 0 and sha else None

    def resolve(self, ref: str) -> str | None:
        done = git.run(self.root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}", check=False)
        sha = git.text(done).strip()
        return sha if done.returncode == 0 and sha else None

    def tree(self, ref: str = "HEAD", prefix: str = "") -> dict[str, str]:
        """``{path: blob id}`` of every file under ``prefix`` at ``ref``."""
        args = ["ls-tree", "-r", "-z", "--full-tree", ref]
        if prefix:
            args += ["--", prefix.rstrip("/")]
        done = git.run(self.root, *args, check=False, literal=True)
        return parse_ls_tree(done.stdout) if done.returncode == 0 else {}

    def read(self, ref: str, path: str) -> bytes | None:
        """``path``'s bytes at ``ref``, or ``None`` where it did not exist."""
        done = git.run(self.root, "cat-file", "blob", f"{ref}:{path}", check=False)
        return done.stdout if done.returncode == 0 else None

    def read_blobs(self, blobs: Sequence[str]) -> dict[str, bytes]:
        """Several blobs in one process (``cat-file --batch``)."""
        if not blobs:
            return {}
        done = git.run(self.root, "cat-file", "--batch", stdin=("\n".join(blobs) + "\n").encode())
        out: dict[str, bytes] = {}
        data, pos = done.stdout, 0
        for blob in blobs:
            end = data.index(b"\n", pos)
            header = data[pos:end].decode().split()
            pos = end + 1
            if len(header) < 3 or header[1] == "missing":
                continue
            size = int(header[2])
            out[blob] = data[pos : pos + size]
            pos += size + 1
        return out

    def status(self, pathspecs: Iterable[str] = ()) -> list[tuple[str, str]]:
        """``(code, path)`` for every working-tree file that differs from
        ``HEAD`` (untracked included, renames off)."""
        args = ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames"]
        specs = list(pathspecs)
        if specs:
            args += ["--", *specs]
        done = git.run(self.root, *args, check=False, literal=bool(specs))
        return parse_status(done.stdout) if done.returncode == 0 else []

    def log(
        self,
        *pathspecs: str,
        start: str | None = None,
        limit: int | None = None,
        skip: int = 0,
    ) -> list[Commit]:
        """Commits newest first, from ``start`` (default ``HEAD``), touching
        ``pathspecs`` when given."""
        args = ["log", LOG_FORMAT, "--raw", "--numstat", "--no-renames", "--no-abbrev"]
        if limit is not None:
            args.append(f"-n{limit}")
        if skip:
            args.append(f"--skip={skip}")
        args.append(start or "HEAD")
        if pathspecs:
            args += ["--", *pathspecs]
        done = git.run(self.root, *args, check=False, literal=True)
        return parse_log(done.stdout) if done.returncode == 0 else []

    def commit_of(self, version: str) -> Commit | None:
        if not looks_like_a_version(version):
            return None
        found = self.log(start=version, limit=1)
        return found[0] if found and found[0].version.startswith(version) else None

    def diff(self, version: str, path: str) -> str:
        """The unified diff ``version`` made to ``path`` (empty if none)."""
        if not looks_like_a_version(version):
            return ""
        done = git.run(
            self.root,
            "show",
            "--format=",
            "--patch",
            "--no-color",
            "--no-ext-diff",
            "--no-renames",
            version,
            "--",
            path,
            check=False,
            literal=True,
        )
        return git.text(done) if done.returncode == 0 else ""

    def diff_trees(self, a: str, b: str, *pathspecs: str) -> str:
        """The unified diff between two commits or trees."""
        args = ["diff", "--no-color", "--no-ext-diff", "--no-renames", a, b]
        if pathspecs:
            args += ["--", *pathspecs]
        done = git.run(self.root, *args, check=False, literal=True)
        return git.text(done) if done.returncode in (0, 1) else ""

    def later(self, version: str, path: str) -> str | None:
        """The newest commit after ``version`` that touched ``path``."""
        done = git.run(
            self.root,
            "log",
            "--format=%H",
            "-n1",
            f"{version}..HEAD",
            "--",
            path,
            check=False,
            literal=True,
        )
        found = git.text(done).strip()
        return found or None

    # --- staging (the writer's primitives) ------------------------------------

    def stage(self, paths: Iterable[str]) -> None:
        """Stage exactly ``paths``: added or modified where the file exists,
        removed where it does not. A path the exclude file ignores is never
        staged either way — switching ``credentials/`` off stops recording
        ciphertext, it never records its deletion (which would delete the
        other machines' copies on their next round)."""
        root = self.root
        wanted = list(dict.fromkeys(paths))
        ignored = self.ignored(wanted)
        wanted = [p for p in wanted if p not in ignored]
        present = [p for p in wanted if (root / p).exists() or (root / p).is_symlink()]
        missing = [p for p in wanted if p not in present]
        for chunk in _chunks(present):
            git.run(root, "add", "-A", "--", *chunk, literal=True)
        for chunk in _chunks(missing):
            git.run(
                root, "rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", *chunk, literal=True
            )

    def ignored(self, paths: Sequence[str]) -> set[str]:
        """The subset of paths the exclude file keeps out of every commit
        (a path that is ignored is staged as absent, so a tracked file that
        became ignored — credentials/ switched off — leaves the index)."""
        if not paths:
            return set()
        done = git.run(
            self.root,
            "check-ignore",
            "-z",
            "--stdin",
            "--no-index",
            stdin=("\0".join(paths) + "\0").encode(),
            check=False,
        )
        return {p for p in done.stdout.decode("utf-8", "replace").split("\0") if p}

    def commit_staged(self, meta: CommitMeta, *, allow_empty: bool = False) -> str | None:
        """Commit what is staged; ``None`` when nothing is (the usual no-op)."""
        root = self.root
        if (
            not allow_empty
            and git.run(root, "diff", "--cached", "--quiet", check=False).returncode == 0
        ):
            return None
        args = ["commit", "-q", "--no-verify", "-F", "-"]
        if allow_empty:
            args.insert(2, "--allow-empty")
        git.run(root, *args, stdin=message(meta).encode(), writer=meta.writer)
        return self.head()

    def unstage(self, paths: Iterable[str]) -> None:
        for chunk in _chunks(list(paths)):
            git.run(self.root, "reset", "-q", "--", *chunk, check=False, literal=True)


def _chunks(items: list[str], size: int = 200) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _manifest_bytes() -> bytes:
    return (f'{{\n  "schema_version": {MANIFEST_SCHEMA_VERSION}\n}}\n').encode()


__all__ = ["VaultRepository"]
