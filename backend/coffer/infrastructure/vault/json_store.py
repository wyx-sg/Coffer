"""One JSON file of machine-local state under ``local/`` (spec vault-storage).

Local state is true of this machine only — reach, the sync remote, retention,
the secret boundary's approvals — so it is never in the vault repository and
never committed. It is small, read often and written rarely, so each area is
one JSON object in one file: read whole, changed under a lock, written back
atomically. A missing file reads as the empty object; a file that does not
parse is moved aside as ``<name>.unreadable-<n>`` and read as empty, because
local state can be set again and a daemon that refuses to start over a
settings file is worse than one that forgets them — the move is logged.
"""

from __future__ import annotations

import copy
import json
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from coffer.infrastructure.vault.atomic import atomic_write

logger = logging.getLogger(__name__)

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.RLock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(str(path), threading.RLock())


class JsonStore:
    """A JSON object in one file, changed atomically.

    ``path`` may be a callable so the file follows ``HOME`` (tests, the
    migration's rehearsal) instead of being fixed at construction.
    """

    def __init__(self, path: Path | Callable[[], Path], *, mode: int = 0o600) -> None:
        self._path = path if callable(path) else (lambda: path)
        self._mode = mode

    @property
    def path(self) -> Path:
        return self._path()

    def read(self) -> dict[str, Any]:
        path = self.path
        with _lock_for(path):
            return self._load(path)

    def write(self, value: dict[str, Any]) -> None:
        path = self.path
        with _lock_for(path):
            self._dump(path, value)

    def update(self, change: Callable[[dict[str, Any]], dict[str, Any] | None]) -> dict[str, Any]:
        """Apply ``change`` to a copy of the object under the file's lock and
        write the result (``change`` may mutate in place and return ``None``)."""
        path = self.path
        with _lock_for(path):
            current = self._load(path)
            draft = copy.deepcopy(current)
            result = change(draft)
            new = draft if result is None else result
            if new != current:
                self._dump(path, new)
            return new

    def _load(self, path: Path) -> dict[str, Any]:
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return {}
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            value = None
        if isinstance(value, dict):
            return value
        aside = _aside(path)
        path.rename(aside)
        logger.warning("local_state.unreadable_moved_aside", extra={"path": str(aside)})
        return {}

    def _dump(self, path: Path, value: dict[str, Any]) -> None:
        data = (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()
        atomic_write(path, data, mode=self._mode)


def _aside(path: Path) -> Path:
    n = 1
    while True:
        candidate = path.with_name(f"{path.name}.unreadable-{n}")
        if not candidate.exists():
            return candidate
        n += 1


__all__ = ["JsonStore"]
