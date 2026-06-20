"""Shared path-containment helper for the skill subsystem.

``file_ops.py`` and ``validator.py`` each enforce the same invariant: a
candidate path must stay inside a trusted root. They used to reimplement the
same ``Path.is_relative_to`` wrapper. This module holds the single canonical
implementation.

The helper does NOT resolve its arguments — callers decide whether to
``resolve()`` first (they all do, before calling), matching the original
behaviour of each call site.
"""

from __future__ import annotations

import pathlib


def is_within(path: pathlib.Path, root: pathlib.Path) -> bool:
    """True if ``path`` is ``root`` itself or nested under it.

    Both arguments are compared as-is; callers that need symlink-safe
    containment must ``resolve()`` before calling (every current caller does).
    """
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
