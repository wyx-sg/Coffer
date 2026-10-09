"""The resources a run creates on the target, and their removal.

Only names starting with ``qa-`` are ever created. Every name a suite will use
is reserved up front: if any already exists on the target the run refuses to
start, so it can never change or delete something it did not create. Whatever
was created is deleted in ``finally`` (newest first, so a resource goes before
the secret it cites), and the journal is written to the run's directory.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from e2e.installed._common.target import RefusedError

PREFIX = "qa-"

Deleter = Callable[[], Awaitable[int]]
Exists = Callable[[str, str], Awaitable[bool]]


@dataclass
class Entry:
    kind: str
    name: str
    ident: str
    created_at: str
    deleted_by: str | None = None
    delete_status: int | None = None
    error: str | None = None
    _delete: Deleter | None = field(default=None, repr=False, compare=False)


class ResourceJournal:
    def __init__(self, out: Path) -> None:
        self._out = out
        self.reserved: list[tuple[str, str]] = []
        self.entries: list[Entry] = []
        self.leftovers: dict[str, Any] | None = None

    @staticmethod
    def check_name(name: str) -> None:
        if not name.startswith(PREFIX):
            raise RefusedError(f"{name!r}: this suite only creates names starting {PREFIX!r}")

    async def reserve(self, names: Iterable[tuple[str, str]], exists: Exists) -> None:
        """Refuse the run if any ``(kind, name)`` already exists on the target."""
        taken = []
        for kind, name in names:
            self.check_name(name)
            self.reserved.append((kind, name))
            if await exists(kind, name):
                taken.append(f"{kind} {name}")
        self.write()
        if taken:
            raise RefusedError(
                "these test names already exist on the target and are left untouched: "
                + ", ".join(taken)
            )

    def created(self, kind: str, name: str, ident: str, delete: Deleter) -> None:
        self.check_name(name)
        if (kind, name) not in self.reserved:
            raise RefusedError(f"{kind} {name} was not reserved before the run started")
        now = datetime.now(UTC).isoformat()
        self.entries.append(Entry(kind, name, ident, now, _delete=delete))
        self.write()

    def deleted(self, ident: str, status: int) -> None:
        """A case removed one of its own resources itself."""
        for entry in self.entries:
            if entry.ident == ident and entry.deleted_by is None:
                entry.deleted_by, entry.delete_status = "case", status
        self.write()

    async def cleanup(self) -> list[Entry]:
        """Delete everything still present; returns the entries that failed.

        Two passes: a secret still cited by a resource that failed its first
        delete gets a second chance once that resource is gone.
        """
        for _ in range(2):
            for entry in reversed(self.entries):
                if entry.deleted_by is not None and entry.delete_status in (200, 204, 404):
                    continue
                if entry._delete is None:
                    continue
                try:
                    status = await entry._delete()
                except Exception as exc:  # cleanup must never stop halfway
                    entry.error = f"{type(exc).__name__}: {exc}"
                    continue
                entry.deleted_by, entry.delete_status = "cleanup", status
                entry.error = None if status in (200, 204, 404) else f"HTTP {status}"
        self.write()
        return [e for e in self.entries if e.delete_status not in (200, 204, 404)]

    def write(self) -> None:
        doc = {
            "reserved": [{"kind": k, "name": n} for k, n in self.reserved],
            "created": [
                {k: v for k, v in asdict(e).items() if not k.startswith("_")} for e in self.entries
            ],
            "leftovers_after_cleanup": self.leftovers,
        }
        (self._out / "journal.json").write_text(json.dumps(doc, indent=2, default=str))
