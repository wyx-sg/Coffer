"""The process's one writer per vault root.

The write lock, the owned paths and the problems list only mean something if
every writer in the process consults the same instance, so the writer is
looked up here by the vault root it serves — which follows ``HOME``, so a test
in a throwaway home gets its own. The composition root sets the
validator and the machine id once; every store asks for the writer here.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from coffer.infrastructure.vault.home import vault_root
from coffer.infrastructure.vault.repository import VaultRepository
from coffer.infrastructure.vault.writer import VaultWriter

_WRITERS: dict[str, VaultWriter] = {}
_GUARD = threading.Lock()


def _no_machine() -> str | None:
    return None


_machine: Callable[[], str | None] = _no_machine


def set_machine(provider: Callable[[], str | None]) -> None:
    """Name this machine in every commit's ``Coffer-Machine`` trailer."""
    global _machine
    _machine = provider


def vault_writer(root: Path | None = None) -> VaultWriter:
    """The writer of the vault at ``root`` (default: this ``HOME``'s)."""
    target = (root or vault_root()).expanduser()
    key = str(target)
    with _GUARD:
        writer = _WRITERS.get(key)
        if writer is None:
            writer = VaultWriter(VaultRepository(target), machine=lambda: _machine())
            _WRITERS[key] = writer
        return writer


def vault_repository(root: Path | None = None) -> VaultRepository:
    return vault_writer(root).repo


def forget(root: Path | None = None) -> None:
    """Drop the writer of ``root`` (all of them without one) — for a test,
    or after a rollback moved the vault aside."""
    with _GUARD:
        if root is None:
            _WRITERS.clear()
        else:
            _WRITERS.pop(str(root.expanduser()), None)


__all__ = ["forget", "set_machine", "vault_repository", "vault_writer"]
