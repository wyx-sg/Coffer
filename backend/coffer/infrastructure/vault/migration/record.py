"""``local/migration.json``: what the upgrade did, in order, so
``coffer migrate --rollback`` can undo exactly that (ADR
every-vault-file-carries-its-format-version "Rollback of a migration is a
restore, never a downgrade").

The record is written before the first move and after every one, so an
upgrade that stops half-way still names every tree it moved: a rollback of a
failed upgrade is the same rollback.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coffer.infrastructure.vault.json_store import JsonStore
from coffer.infrastructure.vault.migration.places import RECORD, at

RECORD_FORMAT = 1


def now() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


@dataclass
class Move:
    source: str
    target: str


@dataclass
class Stamped:
    """A knowledge document whose curation stamp was stripped: its original
    is in the backup set, and ``blob`` is what the stripped file held."""

    path: str
    blob: str


@dataclass
class Record:
    build: str
    started_at: str
    database_backup: str | None = None
    daemon_config_backup: bool = False
    #: Class directories the home did not have before; rollback moves each aside.
    created: list[str] = field(default_factory=list)
    moves: list[Move] = field(default_factory=list)
    knowledge_git: str | None = None
    stamped: list[Stamped] = field(default_factory=list)
    database_renamed: bool = False
    finished_at: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {"format_version": RECORD_FORMAT, **asdict(self)}

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> Record:
        return cls(
            build=str(raw.get("build") or ""),
            started_at=str(raw.get("started_at") or ""),
            database_backup=raw.get("database_backup"),
            daemon_config_backup=bool(raw.get("daemon_config_backup")),
            created=list(raw.get("created") or []),
            moves=[Move(**m) for m in raw.get("moves") or []],
            knowledge_git=raw.get("knowledge_git"),
            stamped=[Stamped(**s) for s in raw.get("stamped") or []],
            database_renamed=bool(raw.get("database_renamed")),
            finished_at=raw.get("finished_at"),
        )


class RecordFile:
    """The record of one home's upgrade."""

    def __init__(self, home: Path) -> None:
        self._store = JsonStore(at(home, RECORD))

    def exists(self) -> bool:
        return self._store.path.is_file()

    def read(self) -> Record | None:
        raw = self._store.read()
        return Record.from_json(raw) if raw else None

    def write(self, record: Record) -> None:
        self._store.write(record.to_json())


__all__ = ["RECORD_FORMAT", "Move", "Record", "RecordFile", "Stamped", "now"]
