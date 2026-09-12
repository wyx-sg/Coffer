"""Atomic, user-only JSON writes for the small files in ``~/.coffer/``.

Shared by the daemon's discovery file (``daemon.json``) and its configuration
file (``daemon-config.json``). Both are read by other processes at arbitrary
moments, and both hold something the rest of the machine has no business
reading, so both need the same two properties.

``tempfile.mkstemp`` (``O_CREAT|O_EXCL``, mode ``0600``) stages the content, so
the file never exists with a mode broader than ``0600`` — the older
``write_text`` + ``chmod`` pair widened that window depending on the caller's
umask (CODE-018). The staging file takes a UNIQUE per-call name in the target
directory, so two processes racing to publish the same path never collide on a
shared ``<name>.tmp``: a fixed name plus ``O_EXCL`` crashed the loser with
``FileExistsError``, or let one unlink the other's staging file. The final
``os.replace`` is atomic, so the last writer wins cleanly and no partial file is
ever visible at ``path``.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_0600(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` as JSON to ``path``, atomically, mode ``0600``.

    Creates the parent directory if needed; the caller owns nothing else.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(payload, indent=2))
    except Exception:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        raise
    os.replace(str(tmp), str(path))
