"""Keep a frozen daemon's unpacked files from being swept by the OS.

A PyInstaller one-file binary extracts itself into ``$TMPDIR/_MEI*`` on start.
macOS periodically deletes files there that have not been accessed for about
three days, and a daemon that runs longer than that finds its own files gone:
the CA bundle first (``ssl.create_default_context`` raises ``FileNotFoundError``
the next time an HTTP client is built, e.g. when a channel is reconfigured),
then any extension module it has not loaded yet.

Touching every unpacked file well inside that window keeps the tree alive.
Unfrozen runs have no such directory, so this does nothing there.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
from pathlib import Path

_logger = logging.getLogger(__name__)

# The sweep threshold is about 3 days; a 6 hour pass leaves ample margin.
TOUCH_INTERVAL_SECONDS = 6 * 60 * 60


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


async def keep_unpack_dir_alive(interval: float = TOUCH_INTERVAL_SECONDS) -> None:
    """Touch the unpack directory now and then, until cancelled."""
    root = unpack_dir()
    if root is None:
        return
    while True:
        count = await asyncio.to_thread(touch_tree, root)
        _logger.info("unpack_keepalive touched=%d dir=%s", count, root)
        await asyncio.sleep(interval)
