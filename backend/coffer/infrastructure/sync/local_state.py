"""This machine's sync state under ``local/sync/`` (never synced): the remote,
and the round waiting for a person (implements ``RemoteStorePort`` and
``RoundStatePort``)."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.stops import ConflictFile, Stop, conflict_from_json, stop_from_json, to_json
from coffer.infrastructure.vault.home import derived_root, local_root
from coffer.infrastructure.vault.json_store import JsonStore


class JsonRemoteStore:
    def __init__(self, path: Callable[[], Path] | None = None) -> None:
        self._store = JsonStore(path or (lambda: local_root() / "sync" / "remote.json"))

    def get(self) -> SyncRemote | None:
        raw = self._store.read()
        return SyncRemote.from_json(raw) if raw.get("url") else None

    def put(self, remote: SyncRemote) -> None:
        self._store.write(remote.to_json())

    def clear(self) -> None:
        self._store.write({})


class JsonRoundState:
    def __init__(self, path: Callable[[], Path] | None = None) -> None:
        self._store = JsonStore(path or (lambda: local_root() / "sync" / "round.json"))

    def _get(self, key: str) -> Any:
        return self._store.read().get(key)

    def _set(self, key: str, value: Any) -> None:
        def change(doc: dict[str, Any]) -> None:
            if value is None:
                doc.pop(key, None)
            else:
                doc[key] = value

        self._store.update(change)

    def stop(self) -> Stop | None:
        raw = self._get("stop")
        return stop_from_json(raw) if raw else None

    def set_stop(self, stop: Stop | None) -> None:
        self._set("stop", to_json(stop) if stop is not None else None)

    def join_choices(self) -> tuple[ConflictFile, ...]:
        return tuple(conflict_from_json(c) for c in self._get("join_choices") or ())

    def set_join_choices(self, choices: Sequence[ConflictFile]) -> None:
        self._set("join_choices", [to_json(c) for c in choices] or None)

    def confirmed(self) -> tuple[str, str] | None:
        pair = self._get("confirmed")
        return (pair[0], pair[1]) if isinstance(pair, list) and len(pair) == 2 else None

    def set_confirmed(self, pair: tuple[str, str] | None) -> None:
        self._set("confirmed", list(pair) if pair else None)

    def joined(self) -> bool:
        return bool(self._get("joined"))

    def set_joined(self, joined: bool) -> None:
        self._set("joined", True if joined else None)


class ConflictScratch:
    """``derived/sync-conflicts/<path>``."""

    def __init__(self, root: Callable[[], Path] | None = None) -> None:
        self._root = root or (lambda: derived_root() / "sync-conflicts")

    def _path(self, path: str) -> Path:
        target = (self._root() / path).resolve()
        if not str(target).startswith(str(self._root().resolve())):
            raise ValueError(f"not a vault path: {path}")
        return target

    def write(self, path: str, data: bytes) -> str:
        target = self._path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return str(target)

    def read(self, path: str) -> bytes | None:
        target = self._path(path)
        return target.read_bytes() if target.is_file() else None

    def where(self, path: str) -> str | None:
        """The copy's absolute path, once it has been written."""
        target = self._path(path)
        return str(target) if target.is_file() else None

    def clear(self) -> None:
        shutil.rmtree(self._root(), ignore_errors=True)


__all__ = ["ConflictScratch", "JsonRemoteStore", "JsonRoundState"]
