"""The text a session is handed at start (spec memory "Hand a session its
project's memories at start").

Used by the session-start hook (``coffer memory session-start``, which runs
without the daemon) and by Coffer's own turns (chat, channels, scheduled
tasks), which put the same text in the system prompt. The working directory
decides the project: the repository it is in, keyed as the hub keys it. A
directory in no repository, and the vault's own checkout, get nothing.
"""

from __future__ import annotations

import os
import pathlib

from coffer.domain.memory.context import render_context
from coffer.domain.memory.errors import UnsafeMemoryPath
from coffer.domain.memory.hub import PROJECTS, hub_project_key, project_folder
from coffer.domain.vault.layout import MEMORY
from coffer.infrastructure.memory.hub_store import read_topics
from coffer.infrastructure.memory.repository import resolve_repository

#: Set in the environment of a session Coffer starts itself, whose system
#: prompt already carries the memories: the hook then prints nothing, so the
#: session is not handed them twice.
INJECTED_ENV = "COFFER_MEMORY_IN_PROMPT"


def _display(path: pathlib.Path, home: pathlib.Path) -> str:
    try:
        return f"~/{path.relative_to(home).as_posix()}"
    except ValueError:
        return str(path)


def project_of(cwd: str | pathlib.Path, *, vault: pathlib.Path) -> tuple[str, str] | None:
    """``(key, folder)`` of the project ``cwd`` is in, or ``None``."""
    repo = resolve_repository(cwd)
    if repo is None:
        return None
    try:
        if pathlib.Path(repo.root).resolve() == vault.resolve():
            return None
    except OSError:
        return None
    key = hub_project_key(remote_url=repo.remote_url, root_name=pathlib.Path(repo.root).name)
    if not key:
        return None
    try:
        return key, project_folder(key)
    except UnsafeMemoryPath:
        return None


def session_context(
    cwd: str | pathlib.Path, *, vault: pathlib.Path, home: pathlib.Path | None = None
) -> str:
    """The memories handed to a session started in ``cwd``; ``""`` when it is
    in no project."""
    found = project_of(cwd, vault=vault)
    if found is None:
        return ""
    key, folder = found
    path = vault / MEMORY / PROJECTS / folder
    home = home or pathlib.Path(os.environ.get("HOME", os.path.expanduser("~")))
    return render_context(
        project=key, folder=_display(path, home), topics=read_topics(path, folder)
    )


__all__ = ["INJECTED_ENV", "project_of", "session_context"]
