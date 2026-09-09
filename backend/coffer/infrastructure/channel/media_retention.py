"""Infrastructure sweep for the channel-media dir (spec 009 — FR-033).

The pure decision (which files are too old) lives in
``coffer.domain.channel.media_retention``; this module does the I/O: stat every
file in the media dir, ask the domain helper which to delete, unlink them, and
return the deleted paths so the caller can log/count. Wired into the retention
cadence at composition root (the application ``RetentionService`` receives this
as an injected callable, keeping application free of infrastructure imports).
"""

from __future__ import annotations

import logging
import pathlib
from datetime import UTC, datetime

from coffer.domain.channel.media_retention import MEDIA_RETENTION_DAYS, files_to_prune
from coffer.infrastructure.channel.seatalk_media import default_media_dir

_logger = logging.getLogger(__name__)


def prune_media_dir(
    media_dir: pathlib.Path,
    *,
    max_age_days: int,
    now: datetime,
) -> list[str]:
    """Delete files in ``media_dir`` older than ``max_age_days`` (by mtime).

    A missing dir is a no-op (nothing downloaded yet). Each file's mtime is read
    once, the pure ``files_to_prune`` decides which to remove, then they are
    unlinked. A single failed stat/unlink is skipped (logged), never wedging the
    sweep. Returns the paths actually deleted.
    """
    if not media_dir.exists():
        return []
    entries: list[tuple[str, datetime]] = []
    for child in media_dir.iterdir():
        if not child.is_file():
            continue
        try:
            mtime = datetime.fromtimestamp(child.stat().st_mtime, tz=UTC)
        except OSError:
            _logger.warning("channel.media.stat_failed path=%s", child, exc_info=True)
            continue
        entries.append((str(child), mtime))

    deleted: list[str] = []
    for path in files_to_prune(entries, max_age_days=max_age_days, now=now):
        try:
            pathlib.Path(path).unlink()
        except OSError:
            _logger.warning("channel.media.unlink_failed path=%s", path, exc_info=True)
            continue
        deleted.append(path)
    if deleted:
        _logger.info("channel.media.pruned count=%d", len(deleted))
    return deleted


def default_media_sweep(now: datetime) -> list[str]:
    """Prune the default channel-media dir (``~/.coffer/channel-media``) with the
    30-day window. Bound at composition root into ``RetentionService`` so the
    application layer stays free of infrastructure imports (FR-033)."""
    return prune_media_dir(default_media_dir(), max_age_days=MEDIA_RETENTION_DAYS, now=now)


__all__ = ["default_media_sweep", "prune_media_dir"]
