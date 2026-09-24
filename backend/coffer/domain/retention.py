"""Retention-policy domain entity and the media-dir age rule (kind-agnostic)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class RetentionPolicy:
    """One row in the retention_policies table.

    `retention_days`:
        - None → keep forever (no auto-prune)
        - positive int → keep N days, prune older entries
        - 0 is forbidden at the application layer; CHECK constraint in
          the migration also rejects it.
    """

    table_name: str
    retention_days: int | None
    last_pruned_at: datetime | None
    last_pruned_rows: int
    updated_at: datetime


# ---------------------------------------------------------------------------
# Media directories
# ---------------------------------------------------------------------------
#
# Attachment bytes live on disk, out of the chat DB (the chat DB keeps only an
# ``AttachmentBlock`` reference — ADRs channel-attachments and
# chat-attachment-uploads): ``~/.coffer/channel-media`` for what a channel
# downloaded, ``~/.coffer/chat-media`` for what the web composer uploaded. Both
# accumulate, so both are swept on the retention cadence by the same rule. The
# *decision* — which files are old enough to delete — is pure and lives here;
# the ``stat``/``unlink`` I/O is ``coffer.infrastructure.media_retention``. A
# dead reference degrades to a text note on a later read, so a plain mtime age
# prune (no per-conversation reference check) is sufficient.

#: 30-day window by file mtime, no size cap.
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
