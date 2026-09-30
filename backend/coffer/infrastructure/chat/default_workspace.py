"""The Coffer-managed working directory a turn falls back to when none is given.

A chat draft (the per-turn working-directory picker was removed) or a channel
turn (a channel without a configured workspace) names no cwd. Rather than fail
the turn — which leaves a chat bot silently dead — the agent providers default
to a single Coffer-managed workspace under ``~/.coffer/content/workspace``,
created on first use. It is ``content`` (ADR storage-is-five-classes-by-nature):
what an agent leaves there is the user's only copy, and it is not synced. The
path is resolved from ``HOME`` at every call, so a test's throwaway home moves it.
"""

from __future__ import annotations

from coffer.infrastructure.vault.home import content_root


def default_workspace_dir() -> str:
    """Return ``~/.coffer/content/workspace``, creating it (and parents) if absent.

    Returns the absolute path as a string — the shape the providers store as
    ``agent_config.cwd``.
    """
    workspace = content_root() / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return str(workspace)


__all__ = ["default_workspace_dir"]
