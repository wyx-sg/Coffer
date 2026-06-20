"""Atomic file writes for persisted source-of-truth files.

Coffer's invariant is "files are truth, SQLite is a rebuildable index", so a
persisted Markdown / raw file must never be left truncated by a crash or power
loss mid-write. A plain ``path.write_text`` can leave a partial file if the
process dies between the first and last byte. These helpers instead write to a
temp file in the SAME directory, fsync it, then ``os.replace`` it into place: a
reader always sees either the complete old file or the complete new file, never
a partial mix.

Scope: a single fsync of the file + same-filesystem ``os.replace`` gives
ATOMICITY (no partial/corrupt file), which is the goal here. A directory fsync
(rename-durability under power loss — guaranteeing the rename itself survives,
not just that the bytes are on disk) is a stronger guarantee that is
deliberately NOT in scope; it can be layered on later if a real durability need
appears.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from uuid import uuid4


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` atomically: a crash leaves either the old file
    intact or the new file complete, never a truncated mix.

    The temp file is created in the SAME directory so ``os.replace`` is an atomic
    rename on the same filesystem; the data is fsync'd before the rename so it is
    durable. On any failure the temp file is cleaned up and the error re-raised,
    leaving ``path`` untouched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # The temp name carries a per-call uniquifier (uuid) on top of the pid so two
    # concurrent writes to the SAME path (e.g. a fact update racing an organizer
    # INDEX.md rewrite within one process) never collide on the temp file and
    # spuriously fail each other's os.replace.
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid4().hex}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Encode ``text`` and write it to ``path`` atomically (see
    :func:`atomic_write_bytes`)."""
    atomic_write_bytes(path, text.encode(encoding))
