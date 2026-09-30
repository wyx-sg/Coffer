"""The derived per-uid index of resources: where each one was found, its
revision counter and when it last changed (plan D4).

``Resource.rev`` stays an integer because the event stream and the
reconciler's ``Changed`` hint carry one; what it counts is changes to the
resource's file (its blob id) and to its reach on this machine. ``updated_at``
is the time of the last such change. Neither is in the file: two machines
stamping them would conflict on every edit, and git already knows when a file
changed.

The index lives in ``derived/index/resources.json``. Deleting it is safe: the
next read rebuilds it, every resource starting again at revision 1 with its
``updated_at`` set to its ``created_at``. Only the in-process dedupe of hints
reads the counter, so a restart from 1 costs nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coffer.infrastructure.vault.home import derived_root
from coffer.infrastructure.vault.json_store import JsonStore


def index_path(home: Path | None = None) -> Path:
    return derived_root(home) / "index" / "resources.json"


@dataclass(frozen=True)
class Seen:
    """What the store saw of one resource on one read: where, which bytes,
    which reach."""

    uid: str
    path: str
    blob: str
    reach: str
    created_at: datetime | None


@dataclass(frozen=True)
class IndexRow:
    rev: int
    updated_at: datetime
    first_seen: datetime


def _now() -> datetime:
    return datetime.now(tz=UTC)


def parse_time(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class UidIndex:
    """``derived/index/resources.json``: ``{uid: {path, blob, reach, rev,
    updated_at, first_seen}}``."""

    def __init__(self, path: Path | Callable[[], Path] = index_path) -> None:
        self._store = JsonStore(path, mode=0o644)

    def rows(self) -> dict[str, IndexRow]:
        out: dict[str, IndexRow] = {}
        for uid, raw in self._store.read().items():
            row = _row(raw)
            if row is not None:
                out[uid] = row
        return out

    def observe(self, seen: Iterable[Seen], *, forget_others: bool = False) -> dict[str, IndexRow]:
        """Record what was seen: a new uid starts at revision 1, a uid whose
        blob or reach differs from the last sighting is bumped. With
        ``forget_others`` every uid not seen is dropped (a full read)."""
        batch = {s.uid: s for s in seen}
        now = _now()

        def change(doc: dict[str, Any]) -> None:
            if forget_others:
                for uid in [u for u in doc if u not in batch]:
                    del doc[uid]
            for uid, s in batch.items():
                old = doc.get(uid)
                if not isinstance(old, dict) or _row(old) is None:
                    stamp = (s.created_at or now).isoformat()
                    doc[uid] = {
                        "path": s.path,
                        "blob": s.blob,
                        "reach": s.reach,
                        "rev": 1,
                        "updated_at": stamp,
                        "first_seen": stamp,
                    }
                    continue
                if old.get("blob") != s.blob or old.get("reach") != s.reach:
                    old["rev"] = int(old["rev"]) + 1
                    old["updated_at"] = now.isoformat()
                old["path"], old["blob"], old["reach"] = s.path, s.blob, s.reach

        doc = self._store.update(change)
        return {uid: row for uid in batch if (row := _row(doc.get(uid))) is not None}

    def forget(self, uid: str) -> None:
        def change(doc: dict[str, Any]) -> None:
            doc.pop(uid, None)

        self._store.update(change)


def _row(raw: Any) -> IndexRow | None:
    if not isinstance(raw, dict):
        return None
    rev = raw.get("rev")
    updated = parse_time(raw.get("updated_at"))
    first = parse_time(raw.get("first_seen")) or updated
    if not isinstance(rev, int) or isinstance(rev, bool) or updated is None or first is None:
        return None
    return IndexRow(rev=rev, updated_at=updated, first_seen=first)


__all__ = ["IndexRow", "Seen", "UidIndex", "index_path", "parse_time"]
