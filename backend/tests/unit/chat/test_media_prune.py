"""The media-dir prune ages channel attachments out by file mtime."""

from __future__ import annotations

import os
import pathlib
from datetime import UTC, datetime, timedelta

import pytest

from coffer.infrastructure.media_retention import count_media_dir, prune_media_dir


@pytest.mark.acceptance(
    spec="channels",
    scenario="the media dir prune deletes stale files and keeps fresh ones",
)
def test_media_dir_prune_ages_out_by_mtime(tmp_path: pathlib.Path) -> None:
    media_dir = tmp_path / "channel-media"
    media_dir.mkdir()
    now = datetime(2026, 7, 9, tzinfo=UTC)
    stale = media_dir / "old.jpg"
    fresh = media_dir / "new.jpg"
    stale.write_bytes(b"x")
    fresh.write_bytes(b"y")
    old_ts = (now - timedelta(days=31)).timestamp()
    fresh_ts = (now - timedelta(days=1)).timestamp()
    os.utime(stale, (old_ts, old_ts))
    os.utime(fresh, (fresh_ts, fresh_ts))

    assert count_media_dir(media_dir, max_age_days=30, now=now) == (2, 1)
    deleted = prune_media_dir(media_dir, max_age_days=30, now=now)

    assert deleted == [str(stale)]
    assert not stale.exists()
    assert fresh.exists()
