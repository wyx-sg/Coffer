"""Replace a file's bytes so no reader ever sees half of them.

A sibling temp file in the same directory, flushed, then ``os.replace`` — the
one rename every POSIX file system makes atomic. The temp file's name starts
with a dot and ends in ``.tmp``, which the vault's ``info/exclude`` ignores,
so a crash between the write and the rename leaves nothing git would commit.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, data: bytes, *, mode: int | None = None) -> None:
    """Write ``data`` to ``path`` atomically, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


def remove_file(path: Path, *, stop_at: Path | None = None) -> bool:
    """Delete ``path``, then any directories it leaves empty, up to (never
    including) ``stop_at``. Answers whether a file was removed."""
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    parent = path.parent
    while stop_at is None or parent != stop_at:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent
    return True


__all__ = ["atomic_write", "remove_file"]
