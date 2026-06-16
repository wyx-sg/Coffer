"""The Coffer-managed working directory a turn falls back to when none is given.

A chat draft (the per-turn working-directory picker was removed) or a channel
turn (a channel without a configured workspace) names no cwd. Rather than fail
the turn — which leaves a chat bot silently dead — the agent providers default
to a single Coffer-managed workspace under ``~/.coffer/workspace``, created on
first use. ``HOME`` is honored (not ``Path.home()``) so tests redirect it to a
tmp dir and never touch the real ``~/.coffer``.
"""

from __future__ import annotations

import os
import pathlib


def default_workspace_dir() -> str:
    """Return ``~/.coffer/workspace``, creating it (and parents) if absent.

    Returns the absolute path as a string — the shape the providers store as
    ``agent_config.cwd``.
    """
    home = pathlib.Path(os.environ.get("HOME") or "~").expanduser()
    workspace = home / ".coffer" / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return str(workspace)


__all__ = ["default_workspace_dir"]
