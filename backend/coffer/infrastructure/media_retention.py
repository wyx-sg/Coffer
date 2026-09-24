"""The age sweep for Coffer's attachment media directories (kind-agnostic).

Two kinds keep attachment bytes on disk: a channel downloads into
``~/.coffer/channel-media`` (spec channels "Persist inbound attachments as
references") and the web composer uploads into ``~/.coffer/chat-media`` (spec
chat "Prune uploaded chat media on the retention cadence"). Both are pruned by
one rule, so the I/O lives here once rather than inside either kind: stat every
file, ask the pure ``coffer.domain.retention.files_to_prune`` which are too
old, unlink them. The composition root binds one sweep per directory into the
application ``RetentionService``, which stays free of infrastructure imports.
"""

from __future__ import annotations

import logging
import pathlib
from datetime import UTC, datetime

from coffer.domain.retention import files_to_prune

_logger = logging.getLogger(__name__)


def prune_media_dir(
    media_dir: pathlib.Path,
    *,
    max_age_days: int,
    now: datetime,
) -> list[str]:
    """Delete files in ``media_dir`` older than ``max_age_days`` (by mtime).

    A missing dir is a no-op (nothing stored yet). Each file's mtime is read
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
            _logger.warning("media.stat_failed path=%s", child, exc_info=True)
            continue
        entries.append((str(child), mtime))

    deleted: list[str] = []
    for path in files_to_prune(entries, max_age_days=max_age_days, now=now):
        try:
            pathlib.Path(path).unlink()
        except OSError:
            _logger.warning("media.unlink_failed path=%s", path, exc_info=True)
            continue
        deleted.append(path)
    if deleted:
        _logger.info("media.pruned dir=%s count=%d", media_dir.name, len(deleted))
    return deleted


__all__ = ["prune_media_dir"]
