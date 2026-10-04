"""How much memory this machine has, as an agent reads it when it picks a
local model that fits (spec provider-switching "Detect a local model runtime
without changing it").

Read from ``sysconf`` where the OS answers it (macOS, Linux); anywhere it does
not — Windows has no ``os.sysconf`` — the answer is ``None`` and the hand-off
simply leaves the fact out. Never a subprocess: this is asked on a request.
"""

from __future__ import annotations

import os

_GIB = 1024**3


def memory_label() -> str | None:
    """Physical memory rounded to whole GiB, e.g. ``"32 GB"``; ``None`` when unknown."""
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        size = os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, OSError, ValueError):
        return None
    if pages <= 0 or size <= 0:
        return None
    return f"{max(1, round(pages * size / _GIB))} GB"


__all__ = ["memory_label"]
