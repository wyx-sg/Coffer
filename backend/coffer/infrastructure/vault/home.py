"""The five class directories under ``~/.coffer`` (ADR storage-is-five-classes-by-nature).

Every path is resolved from ``HOME`` at the moment it is asked for, never
cached, so a test (or a rehearsal of the migration in a throwaway home) that
repoints ``HOME`` moves every class with it. There is deliberately no per-tree
override: the knowledge collections and the skill master folders are inside
the vault repository, and a tree outside it would be a tree git cannot see.

``daemon-config.json`` and ``daemon.json`` stay directly under ``~/.coffer``:
the first is read before any migration can run (it carries the port the daemon
binds), the second is the rendezvous every surface reads to find the running
daemon. Neither is stored state of any class.
"""

from __future__ import annotations

import os
from pathlib import Path


def coffer_home(home: Path | None = None) -> Path:
    """``~/.coffer`` for ``home`` (default: this process's ``HOME``)."""
    base = home if home is not None else Path(os.environ.get("HOME", "~")).expanduser()
    return base / ".coffer"


def vault_root(home: Path | None = None) -> Path:
    """The vault repository: configuration and content, the only copy."""
    return coffer_home(home) / "vault"


def local_root(home: Path | None = None) -> Path:
    """Machine-local state: never synced, can be set again."""
    return coffer_home(home) / "local"


def content_root(home: Path | None = None) -> Path:
    """Media and the chat workspace: the user's only copy, not synced yet."""
    return coffer_home(home) / "content"


def derived_root(home: Path | None = None) -> Path:
    """Rebuilt from other state; deleting it is always safe."""
    return coffer_home(home) / "derived"


def runs_db_path(home: Path | None = None) -> Path:
    """The history database: audit, invocations, conversations, rounds, usage."""
    return coffer_home(home) / "runs.db"


def legacy_db_path(home: Path | None = None) -> Path:
    """The single database every build before the vault layout wrote."""
    return coffer_home(home) / "coffer.db"


__all__ = [
    "coffer_home",
    "content_root",
    "derived_root",
    "legacy_db_path",
    "local_root",
    "runs_db_path",
    "vault_root",
]
