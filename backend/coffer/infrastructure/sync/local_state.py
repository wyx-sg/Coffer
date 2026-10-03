"""This machine's sync state under ``local/sync/`` (never synced): the remote,
and the round waiting for a person (implements ``RemoteStorePort`` and
``RoundStatePort``)."""

from __future__ import annotations

import shutil
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coffer.domain.sync.remote import SyncRemote
from coffer.domain.sync.stops import ConflictFile, Stop, conflict_from_json, stop_from_json, to_json
from coffer.infrastructure.vault.home import derived_root, local_root
from coffer.infrastructure.vault.json_store import JsonStore


class JsonRemoteStore:
    def __init__(self, path: Callable[[], Path] | None = None) -> None:
        where = path or (lambda: local_root() / "sync" / "remote.json")
        self._store = JsonStore(where)
        # What "Stop syncing" removed, kept so Undo can put it back.
        self._removed = JsonStore(lambda: where().with_name("removed-remote.json"))

    def get(self) -> SyncRemote | None:
        raw = self._store.read()
        return SyncRemote.from_json(raw) if raw.get("url") else None

    def put(self, remote: SyncRemote) -> None:
        self._store.write(remote.to_json())

    def clear(self) -> None:
        self._store.write({})

    def keep_removed(self, snapshot: dict[str, Any]) -> None:
        self._removed.write(snapshot)

    def removed(self) -> dict[str, Any] | None:
        return self._removed.read() or None

    def forget_removed(self) -> None:
        self._removed.write({})


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

    def plaintext_allowed(self) -> frozenset[str]:
        return frozenset(self._get("plaintext_allowed") or ())

    def allow_plaintext(self, blobs: Sequence[str]) -> None:
        """Add ``blobs`` to what "Push anyway" allowed; an allowed blob stays
        allowed (it is already on the remote once pushed)."""
        merged = sorted(self.plaintext_allowed() | set(blobs))
        self._set("plaintext_allowed", merged or None)


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

    def modified(self, path: str) -> str | None:
        """When the copy was last written (ISO time, UTC), once it exists."""
        target = self._path(path)
        if not target.is_file():
            return None
        return datetime.fromtimestamp(target.stat().st_mtime, tz=UTC).isoformat(timespec="seconds")

    def discard(self, path: str) -> None:
        """Forget one file's copy; a missing copy is nothing to do."""
        self._path(path).unlink(missing_ok=True)

    def clear(self) -> None:
        shutil.rmtree(self._root(), ignore_errors=True)


__all__ = ["ConflictScratch", "JsonRemoteStore", "JsonRoundState"]
