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
        - 0 is forbidden at the application layer.
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
# Attachment bytes live on disk (``~/.coffer/channel-media`` for what a channel
# downloaded; ADR channel-attachments) and accumulate, so they are swept on the
# retention cadence. The *decision* — which files are old enough to delete — is
# pure and lives here; the ``stat``/``unlink`` I/O is
# ``coffer.infrastructure.media_retention``. A plain mtime age prune (no
# per-conversation reference check) is sufficient.

#: The attachments policy's default window (by file mtime, no size cap). The
#: user can change it or keep attachments forever (Settings > Data > Local content).
DEFAULT_ATTACHMENT_RETENTION_DAYS = 30

#: The skill working files policy's default window (by file mtime, anywhere under
#: ``~/.coffer/skill-data``). The user can change it or keep them forever
#: (Settings > Data > History).
DEFAULT_SKILL_DATA_RETENTION_DAYS = 30

#: The config backups policy's default window (by backup mtime, under
#: ``~/.coffer/config-backups``); the newest backup of each file is kept however old.
#: The user can change it or keep them forever (Settings > Data > History).
DEFAULT_CONFIG_BACKUPS_RETENTION_DAYS = 30


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
