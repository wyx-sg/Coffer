"""Keep a frozen daemon's unpacked files from being swept by the OS.

A PyInstaller one-file binary extracts itself into ``$TMPDIR/_MEI*`` on start.
macOS periodically deletes files there that have not been accessed for about
three days, and a daemon that runs longer than that finds its own files gone:
the CA bundle first (``ssl.create_default_context`` raises ``FileNotFoundError``
the next time an HTTP client is built, e.g. when a channel is reconfigured),
then any extension module it has not loaded yet.

Touching every unpacked file well inside that window keeps the tree alive.
Unfrozen runs have no such directory, so this does nothing there.

The same pass deletes what other Coffer one-file processes left behind. The
bootloader removes its unpack directory when the program exits, but not when
the process is killed outright, and each leftover is the size of the whole
archive. Every one-file Coffer binary marks its directory with its own pid
(``packaging/rth_unpack_owner.py``, a PyInstaller runtime hook); a marked
directory whose pid no longer runs is deleted. Anything unmarked may belong to
another PyInstaller program, or to a process that has not written its mark yet,
and is left alone.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import psutil

_logger = logging.getLogger(__name__)

# The sweep threshold is about 3 days; a 6 hour pass leaves ample margin.
TOUCH_INTERVAL_SECONDS = 6 * 60 * 60

#: The file each one-file Coffer binary writes into its unpack directory,
#: holding its pid. Keep in step with ``backend/packaging/rth_unpack_owner.py``.
OWNER_MARKER = ".coffer-pid"


def unpack_dir() -> Path | None:
    """The directory this frozen binary unpacked itself into, or None."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else None


def touch_tree(root: Path) -> int:
    """Refresh the access and modification time of everything under ``root``.

    Returns how many entries were refreshed. Entries that vanished (already
    swept) or cannot be touched are skipped.
    """
    touched = 0
    for dirpath, dirnames, filenames in os.walk(root):
        for name in (*dirnames, *filenames):
            with contextlib.suppress(OSError):
                os.utime(os.path.join(dirpath, name), follow_symlinks=False)
                touched += 1
    with contextlib.suppress(OSError):
        os.utime(root)
    return touched


def _marked_pid(directory: Path) -> int | None:
    try:
        return int((directory / OWNER_MARKER).read_text().strip())
    except (OSError, ValueError):
        return None


def sweep_dead_unpack_dirs(
    temp_root: Path | None = None,
    *,
    is_alive: Callable[[int], bool] = psutil.pid_exists,
) -> list[str]:
    """Delete the Coffer-marked ``_MEI*`` directories whose process has exited.

    Returns the names removed. The running binary's own directory is never a
    candidate, whatever its mark says.
    """
    root = temp_root if temp_root is not None else Path(tempfile.gettempdir())
    own = unpack_dir()
    removed: list[str] = []
    try:
        candidates = sorted(root.glob("_MEI*"))
    except OSError:
        return removed
    for directory in candidates:
        if not directory.is_dir() or (own is not None and directory == own):
            continue
        pid = _marked_pid(directory)
        if pid is None or is_alive(pid):
            continue
        shutil.rmtree(directory, ignore_errors=True)
        removed.append(directory.name)
    return removed


async def keep_unpack_dir_alive(interval: float = TOUCH_INTERVAL_SECONDS) -> None:
    """Touch the unpack directory, and sweep dead ones, now and then until cancelled."""
    root = unpack_dir()
    if root is None:
        return
    while True:
        removed = await asyncio.to_thread(sweep_dead_unpack_dirs)
        if removed:
            _logger.info("unpack_sweep removed=%d", len(removed))
        count = await asyncio.to_thread(touch_tree, root)
        _logger.info("unpack_keepalive touched=%d dir=%s", count, root)
        await asyncio.sleep(interval)
