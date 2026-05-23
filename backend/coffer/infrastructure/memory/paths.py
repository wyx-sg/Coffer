"""On-disk layout for the memory kind."""

from __future__ import annotations

import os
import pathlib
import re


def memory_root() -> pathlib.Path:
    override = os.environ.get("COFFER_MEMORY_ROOT")
    if override:
        return pathlib.Path(override).expanduser()
    return pathlib.Path(os.environ.get("HOME", "~")).expanduser() / ".coffer" / "memory"


# Names like ``.``, ``..``, or any all-dot string would resolve to a parent
# directory or the store root itself — both unsafe targets for an rmtree.
# Spec 007 already constrains store names to ``[a-zA-Z0-9_-]+`` at the
# surface; this is defense-in-depth for any future caller that bypasses
# the surface validator (e.g. a CLI or a migration tool).
_DOTS_ONLY = re.compile(r"^\.+$")


def memory_store_dir(store_name: str) -> pathlib.Path:
    """Resolve the on-disk directory for ``store_name``.

    CODE26-018: rejects ``..``, ``./..`` and other traversal payloads by
    verifying the resolved path is a child of ``memory_root()``. Also
    rejects all-dot names (``.``, ``..``, ``...``) which would silently
    collapse to ancestor directories.
    """
    if _DOTS_ONLY.fullmatch(store_name):
        raise ValueError(f"invalid memory store name: {store_name!r}")
    root = memory_root()
    raw = root / store_name
    # Use the *parent-resolved* form for the safety check so a not-yet-created
    # store directory is comparable to ``root`` even when the store_name
    # contains traversal segments. ``Path.resolve(strict=False)`` is portable
    # across macOS/Linux test environments.
    candidate_resolved = raw.resolve()
    root_resolved = root.resolve()
    if not candidate_resolved.is_relative_to(root_resolved):
        raise ValueError(f"memory store name {store_name!r} escapes the memory root")
    return raw
