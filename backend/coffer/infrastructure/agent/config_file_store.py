"""ConfigFileStore — filesystem adapter for agent config files.

Implements `coffer.application.agent.config_file_service.ConfigFileStorePort`.
All writes are atomic (temp file + ``os.replace``) and keep the prior content
as ``<path>.bak`` (rotating to ``.bak.1`` and ``.bak.2``, :data:`BACKUP_COPIES`
in all) so a bad edit — or a run of them — is always recoverable.

A write may carry the fingerprint of the content the caller read before
deciding what to write. The store then refuses (``ConfigFileStale``) when the
file no longer matches: these are the user's own config files, edited in their
editor while Coffer projects into them, and a read → transform → write that
ignored the change would silently discard their edit.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import tempfile
from datetime import UTC, datetime

from coffer.domain.agent.config_files import DirEntryInfo, FileStat
from coffer.domain.workspace_errors import ConfigFileStale

#: How many prior versions ``write_text_atomic`` / ``delete_with_backup`` keep:
#: ``<path>.bak`` is the newest, ``.bak.1`` and ``.bak.2`` older.
BACKUP_COPIES = 3


def _backup_name(path: pathlib.Path, generation: int) -> pathlib.Path:
    suffix = ".bak" if generation == 0 else f".bak.{generation}"
    return path.with_name(path.name + suffix)


class ConfigFileStore:
    """Reads/writes config files on the local filesystem."""

    def read_text(self, path: pathlib.Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except (FileNotFoundError, IsADirectoryError):
            # A directory where a config file is expected is reported as
            # "absent" — same as stat()'s is_file() check — rather than a 500.
            return None

    def stat(self, path: pathlib.Path) -> FileStat | None:
        try:
            st = path.stat()
        except FileNotFoundError:
            return None
        if not pathlib.Path(path).is_file():
            return None
        return FileStat(
            size=st.st_size,
            modified_at=datetime.fromtimestamp(st.st_mtime, tz=UTC),
        )

    def _rotate_backups(self, path: pathlib.Path) -> None:
        """Shift ``.bak`` → ``.bak.1`` → ``.bak.2`` and copy ``path`` to ``.bak``.

        A copy, not a move, so the original stays in place until the atomic
        replace that follows succeeds. The oldest generation falls off.
        """
        for generation in range(BACKUP_COPIES - 1, 0, -1):
            newer = _backup_name(path, generation - 1)
            if newer.exists():
                os.replace(newer, _backup_name(path, generation))
        shutil.copy2(path, _backup_name(path, 0))

    def write_text_atomic(
        self, path: pathlib.Path, text: str, *, expected_fingerprint: str | None = None
    ) -> None:
        """Atomically write ``text`` to ``path``, keeping backups of what was there.

        With ``expected_fingerprint`` (the :meth:`fingerprint` of the content
        the caller read — ``""`` for a file that did not exist), the write is
        refused with :class:`ConfigFileStale` when the file has changed since:
        an optimistic check that turns a lost update into a 409 the caller can
        act on by re-reading. Without it the write is unconditional.
        """
        path = pathlib.Path(path)
        if expected_fingerprint is not None:
            actual = self.fingerprint(self.read_text(path))
            if actual != expected_fingerprint:
                raise ConfigFileStale(str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
        # Back up the prior version (copy, preserving the original until the
        # replace succeeds) so a bad edit is recoverable from <path>.bak.
        if path.exists():
            self._rotate_backups(path)
        # Write to a temp file in the same directory, then atomically replace.
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        tmp = pathlib.Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    @staticmethod
    def fingerprint(text: str | None) -> str:
        """sha256 of the content; "" for a missing file (text=None)."""
        return "" if text is None else hashlib.sha256(text.encode()).hexdigest()

    def list_dir(self, root: pathlib.Path) -> list[DirEntryInfo] | None:
        """Recursive listing of regular ``.md`` files under ``root``.

        Returns None when ``root`` is not a directory. Symlinked files are
        skipped (containment is validated on paths, not followed targets).
        Sorted by relpath for deterministic output.
        """
        if not root.is_dir():
            return None
        out: list[DirEntryInfo] = []
        for p in sorted(root.rglob("*.md")):
            if p.is_symlink() or not p.is_file():
                continue
            st = p.stat()
            out.append(
                DirEntryInfo(
                    relpath=p.relative_to(root).as_posix(),
                    size=st.st_size,
                    modified_at=datetime.fromtimestamp(st.st_mtime, tz=UTC),
                )
            )
        return out

    def delete_with_backup(self, path: pathlib.Path) -> bool:
        """Copy content to ``<path>.bak`` (rotating older backups), then remove
        the file. False if absent."""
        if not path.is_file():
            return False
        try:
            self._rotate_backups(path)
            path.unlink()
        except FileNotFoundError:
            # Vanished between the check and the copy/unlink — same outcome
            # as "already absent".
            return False
        return True

    def remove_tree(self, path: pathlib.Path) -> bool:
        """Remove a directory tree entirely. False when already absent.

        No backup: used only for content Coffer itself rendered and can
        regenerate byte-identically (a Coffer-owned package directory) —
        a ``.bak`` package dir would still be discovered by the agent's
        extension scanner, so tidier to leave nothing behind.
        """
        if not path.is_dir():
            return False
        shutil.rmtree(path, ignore_errors=True)
        return True

    def resolved_within(self, path: pathlib.Path, root: pathlib.Path) -> bool:
        """Whether ``path`` resolves (following symlinks) inside ``root``.

        The containment re-check behind `validate_child_relpath`'s pure path
        math: a symlinked child pointing outside the entry's directory fails
        here even though its relpath looked legal (spec agent-registry FR-035).
        """
        try:
            return path.resolve().is_relative_to(root.resolve())
        except OSError:
            return False
