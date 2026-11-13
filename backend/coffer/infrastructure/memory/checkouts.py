"""Where each project is checked out on this machine (spec memory "Write a
project's memories only where it is checked out").

Found from the working directories the registered agents recorded, never by
crawling the disk: Claude Code's project directories (resolved the way its
reader resolves them, from a session transcript's ``cwd`` or the slug) and the
``cwd:`` of Codex's rollout summaries. Each is resolved to its repository and keyed
by the hub's project key, so a worktree, the main checkout and a second clone
of one upstream are one project. Of several checkouts of one project, the
main checkout wins over a worktree (resolution already answers the main
checkout's root), then the one used most recently.
"""

from __future__ import annotations

import os
import pathlib
from collections.abc import Iterable
from dataclasses import dataclass

from coffer.domain.agent.native_memory import encode_slug, resolve_project_slug
from coffer.domain.memory.hub import CLAUDE_CODE, CODEX, hub_project_key
from coffer.infrastructure.agent_files.claude_code_transcripts import cwd_from_transcripts
from coffer.infrastructure.agent_files.codex_rollout_summaries import all_rollout_cwds
from coffer.infrastructure.memory.repository import resolve_repository
from coffer.infrastructure.vault.home import vault_root


@dataclass(frozen=True)
class Checkout:
    """One repository on this machine: its hub key and its main root."""

    key: str
    root: str


def recorded_dirs(agent_type: str, config_dir: str) -> list[str]:
    """The working directories one agent recorded."""
    base = pathlib.Path(config_dir)
    if agent_type == CLAUDE_CODE:
        out: list[str] = []
        projects = base / "projects"
        try:
            dirs = [d for d in projects.iterdir() if d.is_dir()]
        except OSError:
            return []
        for project_dir in dirs:
            root = cwd_from_transcripts(project_dir, encode_slug)
            if root is None:
                _, root = resolve_project_slug(project_dir.name, _list_dirs)
            if root:
                out.append(root)
        return out
    if agent_type == CODEX:
        return codex_v2_dirs(base / "memories_v2")
    return []


def codex_v2_dirs(folder: pathlib.Path) -> list[str]:
    """The working directories Codex's v2 memory recorded: the ``cwd:`` line
    of each rollout summary's header (only the header is read)."""
    return all_rollout_cwds(folder)


def checkouts(directories: Iterable[str]) -> dict[str, str]:
    """``project key → checkout root`` for every directory inside a repository."""
    found: dict[str, list[str]] = {}
    for directory in dict.fromkeys(directories):
        repo = resolve_repository(directory)
        if repo is None or not pathlib.Path(repo.root).is_dir() or _is_vault(repo.root):
            continue
        key = hub_project_key(remote_url=repo.remote_url, root_name=os.path.basename(repo.root))
        if key:
            roots = found.setdefault(key, [])
            if repo.root not in roots:
                roots.append(repo.root)
    return {key: max(roots, key=_last_used) for key, roots in found.items()}


def project_of(directory: str) -> Checkout | None:
    """The project ``directory`` is inside, or ``None``. Coffer's own vault is
    a repository and is no project (spec memory "Sync only project
    memories"): what an agent learns while working in it is about the vault's
    content, which carries its own rules."""
    repo = resolve_repository(directory)
    if repo is None or _is_vault(repo.root):
        return None
    key = hub_project_key(remote_url=repo.remote_url, root_name=os.path.basename(repo.root))
    return Checkout(key=key, root=repo.root) if key else None


def _is_vault(root: str) -> bool:
    try:
        return pathlib.Path(root).resolve() == vault_root().resolve()
    except OSError:
        return False


def _last_used(root: str) -> float:
    try:
        return (pathlib.Path(root) / ".git").stat().st_mtime
    except OSError:
        return 0.0


def _list_dirs(path: str) -> list[str]:
    try:
        return [entry.name for entry in pathlib.Path(path).iterdir() if entry.is_dir()]
    except OSError:
        return []


__all__ = ["Checkout", "checkouts", "project_of", "recorded_dirs"]
