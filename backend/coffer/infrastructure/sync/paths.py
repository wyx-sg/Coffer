"""Sync workspace path resolution (spec 010)."""

from __future__ import annotations

import os
import pathlib


def _expand_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HOME", "~")).expanduser()


def sync_root() -> pathlib.Path:
    """``~/.coffer/sync/`` — the git working tree (override via ``$COFFER_SYNC_ROOT``)."""
    override = os.environ.get("COFFER_SYNC_ROOT")
    if override:
        return pathlib.Path(override).expanduser()
    return _expand_home() / ".coffer" / "sync"
