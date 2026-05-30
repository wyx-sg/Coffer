"""ConfigFileStore — filesystem adapter for agent config files.

Implements `coffer.application.agent.config_file_service.ConfigFileStorePort`.
All writes are atomic (temp file + ``os.replace``) and keep a ``<path>.bak``
copy of the prior content so a bad edit is always recoverable.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import tempfile
from datetime import UTC, datetime

from coffer.domain.agent.config_files import FileStat


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

    def write_text_atomic(self, path: pathlib.Path, text: str) -> None:
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Back up the prior version (copy, preserving the original until the
        # replace succeeds) so a bad edit is recoverable from <path>.bak.
        if path.exists():
            shutil.copy2(path, path.with_name(path.name + ".bak"))
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
