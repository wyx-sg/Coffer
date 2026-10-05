"""What this machine last learned about each Git-imported skill's source, in
``local/skill-source-status.json`` (spec skill-manager "Hand a Git-imported
skill's update to an agent").

The record is an observation made here — when this machine last checked, what
it found — so it is local state keyed by the skill's uid: never in the vault,
never synced. The skill kind removes a record when its skill is deleted.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coffer.domain.skill.source_status import SourceStatus
from coffer.infrastructure.vault.home import local_root
from coffer.infrastructure.vault.json_store import JsonStore


def source_status_path() -> Path:
    return local_root() / "skill-source-status.json"


def _time(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _int(raw: Any) -> int:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else 0


def _str(raw: Any) -> str | None:
    return raw if isinstance(raw, str) else None


def _commits(raw: Any) -> tuple[tuple[str, str], ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(
        (c[0], c[1])
        for c in raw
        if isinstance(c, list) and len(c) == 2 and all(isinstance(x, str) for x in c)
    )


def _to_domain(uid: str, raw: dict[str, Any]) -> SourceStatus:
    return SourceStatus(
        skill_uid=uid,
        checked_at=_time(raw.get("checked_at")),
        last_success_at=_time(raw.get("last_success_at")),
        error=_str(raw.get("error")),
        latest_commit=_str(raw.get("latest_commit")),
        commits_ahead=_int(raw.get("commits_ahead")),
        files_changed=_int(raw.get("files_changed")),
        commits=_commits(raw.get("commits")),
    )


def _to_json(status: SourceStatus) -> dict[str, Any]:
    return {
        "checked_at": _iso(status.checked_at),
        "last_success_at": _iso(status.last_success_at),
        "error": status.error,
        "latest_commit": status.latest_commit,
        "commits_ahead": status.commits_ahead,
        "files_changed": status.files_changed,
        "commits": [list(c) for c in status.commits],
    }


class SkillSourceStatusRepo:
    """``SourceStatusRepoPort`` over ``local/skill-source-status.json``."""

    def __init__(self, path: Path | Callable[[], Path] = source_status_path) -> None:
        self._store = JsonStore(path)

    async def get(self, skill_uid: str) -> SourceStatus | None:
        raw = self._store.read().get(skill_uid)
        return _to_domain(skill_uid, raw) if isinstance(raw, dict) else None

    async def list_all(self) -> dict[str, SourceStatus]:
        return {
            uid: _to_domain(uid, raw)
            for uid, raw in self._store.read().items()
            if isinstance(raw, dict)
        }

    async def put(self, status: SourceStatus) -> SourceStatus:
        def change(doc: dict[str, Any]) -> None:
            doc[status.skill_uid] = _to_json(status)

        self._store.update(change)
        return status

    async def delete(self, skill_uid: str) -> None:
        def change(doc: dict[str, Any]) -> None:
            doc.pop(skill_uid, None)

        self._store.update(change)


__all__ = ["SkillSourceStatusRepo", "source_status_path"]
