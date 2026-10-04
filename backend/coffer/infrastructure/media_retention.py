"""The age sweep for Coffer's attachment media directories (kind-agnostic).

Two kinds keep attachment bytes on disk: a channel downloads into
``~/.coffer/content/channel-media`` (spec channels "Persist inbound attachments as
references") and the web composer uploads into ``~/.coffer/content/chat-media`` (spec
chat "Prune uploaded chat media on the retention cadence"). Both are pruned by
one rule, so the I/O lives here once rather than inside either kind: stat every
file, ask the pure ``coffer.domain.retention.files_to_prune`` which are too
old, unlink them. The composition root binds one sweep per directory into the
application ``RetentionService``, which stays free of infrastructure imports.
"""

from __future__ import annotations

import logging
import os
import pathlib
from datetime import UTC, datetime

from coffer.domain.retention import files_to_prune

_logger = logging.getLogger(__name__)


def _stat_files(media_dir: pathlib.Path) -> list[tuple[str, datetime]]:
    """``(path, mtime)`` of every file directly in ``media_dir`` (none if missing)."""
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
    return entries


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
    entries = _stat_files(media_dir)
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


def count_media_dir(
    media_dir: pathlib.Path,
    *,
    max_age_days: int,
    now: datetime,
) -> tuple[int, int]:
    """``(files in media_dir, files older than max_age_days)``: what a sweep would delete."""
    entries = _stat_files(media_dir)
    return len(entries), len(files_to_prune(entries, max_age_days=max_age_days, now=now))


def _stat_tree(root: pathlib.Path) -> list[tuple[str, datetime]]:
    """``(path, mtime)`` of every regular file anywhere under ``root`` (none if missing).

    Symlinks are neither followed nor listed: a link to a directory is not
    descended into and a link to a file is not a file of the tree.
    """
    if root.is_symlink() or not root.is_dir():
        return []
    entries: list[tuple[str, datetime]] = []
    for dirpath, _dirs, filenames in os.walk(root, followlinks=False):
        for name in filenames:
            child = pathlib.Path(dirpath) / name
            try:
                if child.is_symlink() or not child.is_file():
                    continue
                mtime = datetime.fromtimestamp(child.stat().st_mtime, tz=UTC)
            except OSError:
                _logger.warning("media.stat_failed path=%s", child, exc_info=True)
                continue
            entries.append((str(child), mtime))
    return entries


def _remove_empty_dirs(root: pathlib.Path) -> None:
    """Remove directories under ``root`` that hold nothing; ``root`` itself stays."""
    for dirpath, _dirs, _files in os.walk(root, topdown=False, followlinks=False):
        directory = pathlib.Path(dirpath)
        if directory == root or directory.is_symlink():
            continue
        try:
            directory.rmdir()  # fails on a non-empty directory, which is the point
        except OSError:
            continue


def prune_media_tree(
    root: pathlib.Path,
    *,
    max_age_days: int,
    now: datetime,
) -> list[str]:
    """Delete files anywhere under ``root`` older than ``max_age_days`` (by mtime).

    The recursive sweep for a directory whose owners keep subfolders (skill
    working files, ``skill-data/<skill>/``). Directories left empty are removed,
    never ``root`` itself; symlinks are left alone. Returns the files deleted.
    """
    deleted: list[str] = []
    for path in files_to_prune(_stat_tree(root), max_age_days=max_age_days, now=now):
        try:
            pathlib.Path(path).unlink()
        except OSError:
            _logger.warning("media.unlink_failed path=%s", path, exc_info=True)
            continue
        deleted.append(path)
    if deleted:
        _remove_empty_dirs(root)
        _logger.info("media.pruned dir=%s count=%d", root.name, len(deleted))
    return deleted


def count_media_tree(
    root: pathlib.Path,
    *,
    max_age_days: int,
    now: datetime,
) -> tuple[int, int]:
    """``(files under root, files older than max_age_days)``: what a tree sweep would delete."""
    entries = _stat_tree(root)
    return len(entries), len(files_to_prune(entries, max_age_days=max_age_days, now=now))


__all__ = ["count_media_dir", "count_media_tree", "prune_media_dir", "prune_media_tree"]
