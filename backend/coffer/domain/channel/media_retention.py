"""Pure retention decision for the channel-media dir (spec 009 — FR-033).

Channel media bytes live under ``~/.coffer/channel-media`` (out-of-band; the
chat DB keeps only an ``AttachmentBlock`` reference — ADR-041). Those bytes
accumulate, so they are swept on the retention cadence. The *decision* — which
files are old enough to delete — is pure and lives here so it is trivially
testable; the actual ``stat``/``unlink`` I/O is an infrastructure sweep that
calls this. Bytes are re-downloadable and a dead reference degrades gracefully,
so a plain mtime age prune (no per-conversation reference check) is sufficient.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

# 30-day window by file mtime, no size cap (locked design D3, 2026-07-09).
MEDIA_RETENTION_DAYS = 30


def files_to_prune(
    entries: Sequence[tuple[str, datetime]],
    *,
    max_age_days: int,
    now: datetime,
) -> list[str]:
    """Given ``(path, mtime)`` pairs, return the paths older than the window.

    ``entries`` are already-stat'd files (path + last-modified time); a file is
    pruned when its mtime is at or before ``now - max_age_days``. Pure: no I/O,
    deterministic in ``now`` so tests can freeze the clock.
    """
    cutoff = now - timedelta(days=max_age_days)
    return [path for path, mtime in entries if mtime <= cutoff]


__all__ = ["MEDIA_RETENTION_DAYS", "files_to_prune"]
