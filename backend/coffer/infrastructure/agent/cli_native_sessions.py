"""The own sessions of OpenCode, DeepSeek Harness and Cursor, read from their
stores (spec agent-registry "List the sessions an agent keeps in its own
store"; ADR sessions-of-cursor-opencode-and-deepseek-harness-are-read-from-their-stores).

None of the three lists every project's sessions on its command line, so the
list reads the store each one keeps, read-only:

* **OpenCode** — its SQLite database, ``opencode.db`` in its data folder
  (``$XDG_DATA_HOME/opencode``, by default ``~/.local/share/opencode``). 1.x
  keeps sessions in the ``session`` table, 2.x in ``session_v2``; both have the
  columns read here. Only top-level, unarchived sessions are listed, as
  OpenCode's own ``session list`` shows them.
* **DeepSeek Harness** — one folder per session under ``$DSH_HOME/sessions/<the
  folder's key>/``; the title and folder come from the projection DeepSeek
  Harness caches beside it (``storages/session_projcache/sessions/<id>.json``),
  the last activity from the session log's time.
* **Cursor** — one ``store.db`` per chat under ``<config dir>/chats/<the
  folder's hash>/<chat id>/``; its ``meta`` row holds the chat's name and
  creation time as hex-encoded JSON.

Rename and delete go through the agent's own command, as for Claude Code and
Codex. Only OpenCode has one (``opencode session delete``); none of the three
can rename from its command line. Where the agent has no command, the call does
nothing here: the agent keeps its own copy, and Coffer's conversation row (if
one points at the session) takes the new title or goes.

A store that is missing has no sessions. One that cannot be read raises
``StoreUnreadable``, which the composition root answers with the
conversations Coffer ran on the agent (``FallbackSessionSource``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import pathlib
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from coffer.application.agent.native_session_service import SourcePage
from coffer.domain.agent.native_sessions import (
    NativeSession,
    NativeSessionInvalid,
    NativeSessionNotFound,
    is_session_id,
    scrub_secrets,
)
from coffer.domain.pagination import position_of, time_and_id

_FLOOR = datetime.min.replace(tzinfo=UTC)
_DELETE_TIMEOUT_S = 60.0


class StoreUnreadable(Exception):  # noqa: N818
    """The agent's store is there but could not be read as expected."""


def _when_ms(ms: object) -> datetime | None:
    if not isinstance(ms, int | float) or isinstance(ms, bool):
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _mtime(path: pathlib.Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:
        return None


def _order_key(session: NativeSession) -> tuple[datetime, str]:
    return (session.last_activity_at or session.created_at or _FLOOR, session.session_id)


def page_sessions(
    sessions: list[NativeSession], *, q: str | None, limit: int, position: list[Any] | None
) -> SourcePage:
    """Filter (title and folder, case-insensitive), order newest activity first
    with the id as tie-break, and cut one keyset page."""
    after = time_and_id(position, str)
    if q:
        needle = q.lower()
        sessions = [
            s for s in sessions if needle in s.title.lower() or needle in (s.cwd or "").lower()
        ]
    sessions = sorted(sessions, key=_order_key, reverse=True)
    total = len(sessions)
    if after is not None:
        sessions = [s for s in sessions if _order_key(s) < after]
    window = sessions[:limit]
    more = len(sessions) > limit
    return SourcePage(
        items=window,
        next_position=position_of(*_order_key(window[-1])) if more else None,
        total=total,
    )


# --- OpenCode ---------------------------------------------------------------


def opencode_data_dir(env: dict[str, str] | None = None) -> pathlib.Path:
    """OpenCode's data folder: ``$XDG_DATA_HOME/opencode`` or
    ``~/.local/share/opencode``."""
    source = os.environ if env is None else env
    base = source.get("XDG_DATA_HOME") or str(pathlib.Path.home() / ".local" / "share")
    return pathlib.Path(base) / "opencode"


def _read_only(db: pathlib.Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True, timeout=5)


def _opencode_table(conn: sqlite3.Connection) -> str | None:
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in ("session_v2", "session"):
        if table in names:
            return table
    return None


def read_opencode_sessions(db: pathlib.Path) -> list[NativeSession]:
    if not db.is_file():
        return []
    try:
        with contextlib.closing(_read_only(db)) as conn:
            table = _opencode_table(conn)
            if table is None:
                return []
            rows = conn.execute(
                f"SELECT id, title, directory, time_created, time_updated FROM {table} "
                "WHERE parent_id IS NULL AND time_archived IS NULL"
            ).fetchall()
    except sqlite3.Error as exc:
        raise StoreUnreadable(f"OpenCode's database could not be read: {exc}") from exc
    return [
        NativeSession(
            session_id=str(sid),
            title=scrub_secrets(str(title or "")),
            cwd=str(directory) if directory else None,
            created_at=_when_ms(created),
            last_activity_at=_when_ms(updated),
        )
        for sid, title, directory, created, updated in rows
        if is_session_id(str(sid))
    ]


def _opencode_is_v2(db: pathlib.Path) -> bool:
    try:
        with contextlib.closing(_read_only(db)) as conn:
            return _opencode_table(conn) == "session_v2"
    except sqlite3.Error:
        return False


class OpenCodeNativeSessions:
    """``NativeSessionSource`` for OpenCode."""

    def __init__(
        self,
        *,
        which: Callable[[str], str | None],
        env: Callable[[], dict[str, str]],
        data_dir: Callable[[], pathlib.Path] = opencode_data_dir,
    ) -> None:
        self._which = which
        self._env = env
        self._data_dir = data_dir

    def _db(self) -> pathlib.Path:
        return self._data_dir() / "opencode.db"

    async def list(
        self, config_dir: pathlib.Path, *, q: str | None, limit: int, position: list[Any] | None
    ) -> SourcePage:
        sessions = await asyncio.to_thread(read_opencode_sessions, self._db())
        return page_sessions(sessions, q=q, limit=limit, position=position)

    async def rename(self, config_dir: pathlib.Path, session_id: str, title: str) -> None:
        return  # OpenCode has no command to rename a session

    async def delete(self, config_dir: pathlib.Path, session_id: str) -> None:
        binary = self._which("opencode")
        if binary is None:
            raise NativeSessionInvalid("OpenCode is not installed")
        argv = [binary, "session", "delete"]
        # 2.x runs its commands against a background service unless told
        # otherwise; ``--standalone`` keeps the delete in this one process.
        if await asyncio.to_thread(_opencode_is_v2, self._db()):
            argv.append("--standalone")
        argv.append(session_id)
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, **self._env(), "OPENCODE_CONFIG_DIR": str(config_dir)},
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), _DELETE_TIMEOUT_S)
        except TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise NativeSessionInvalid("OpenCode did not answer the delete in time") from exc
        if proc.returncode == 0:
            return
        text = out.decode("utf-8", "replace")
        if "not found" in text.lower():
            raise NativeSessionNotFound(session_id)
        raise NativeSessionInvalid(text.strip().splitlines()[-1] if text.strip() else "failed")


# --- DeepSeek Harness -------------------------------------------------------


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _row(rows: dict[str, Any], name: str) -> Any:
    row = rows.get(name)
    return row.get("val") if isinstance(row, dict) else None


def _dsh_projection(home: pathlib.Path, session_id: str) -> dict[str, Any]:
    path = home / "storages" / "session_projcache" / "sessions" / f"{session_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    record = data.get("record") if isinstance(data, dict) else None
    return record if isinstance(record, dict) else {}


def _dsh_title(rows: dict[str, Any]) -> str:
    title = _row(rows, "title")
    if isinstance(title, str) and title.strip():
        return title
    first = _row(rows, "titleInput")
    if isinstance(first, dict) and isinstance(first.get("first"), dict):
        text = first["first"].get("text")
        if isinstance(text, str):
            return text.strip().splitlines()[0][:200] if text.strip() else ""
    return ""


def read_dsh_sessions(home: pathlib.Path) -> list[NativeSession]:
    root = home / "sessions"
    if not root.is_dir():
        return []
    sessions: list[NativeSession] = []
    try:
        folders = [f for group in root.iterdir() if group.is_dir() for f in group.iterdir()]
    except OSError as exc:
        raise StoreUnreadable(f"DeepSeek Harness's sessions could not be read: {exc}") from exc
    for folder in folders:
        sid = folder.name
        if not folder.is_dir() or not sid.startswith("session-") or not is_session_id(sid):
            continue
        record = _dsh_projection(home, sid)
        identity = _dict(record.get("identity"))
        rows = _dict(record.get("rows"))
        subagent = _row(rows, "subagent")
        if isinstance(subagent, dict) and subagent.get("parentSessionId"):
            continue  # a subagent's session belongs to its parent's
        logs = sorted(folder.glob("session.*.jsonl*"))
        cwd = identity.get("cwd") or _row(rows, "workingDirectory")
        sessions.append(
            NativeSession(
                session_id=sid,
                title=scrub_secrets(_dsh_title(rows)),
                cwd=str(cwd) if isinstance(cwd, str) and cwd else None,
                created_at=_when_ms(identity.get("createdAt")) or _mtime(folder),
                last_activity_at=_mtime(logs[-1]) if logs else _mtime(folder),
            )
        )
    return sessions


class DshNativeSessions:
    """``NativeSessionSource`` for DeepSeek Harness (``config_dir`` is its
    ``DSH_HOME``)."""

    async def list(
        self, config_dir: pathlib.Path, *, q: str | None, limit: int, position: list[Any] | None
    ) -> SourcePage:
        sessions = await asyncio.to_thread(read_dsh_sessions, config_dir)
        return page_sessions(sessions, q=q, limit=limit, position=position)

    async def rename(self, config_dir: pathlib.Path, session_id: str, title: str) -> None:
        return  # DeepSeek Harness has no command to rename a session

    async def delete(self, config_dir: pathlib.Path, session_id: str) -> None:
        return  # nor one to delete it


# --- Cursor -----------------------------------------------------------------


def _cursor_meta(db: pathlib.Path) -> dict[str, Any]:
    with contextlib.closing(_read_only(db)) as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = '0'").fetchone()
    if row is None:
        return {}
    raw = row[0]
    text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    try:
        decoded = bytes.fromhex(text).decode("utf-8")
    except ValueError:
        decoded = text
    data = json.loads(decoded)
    return data if isinstance(data, dict) else {}


def read_cursor_sessions(config_dir: pathlib.Path) -> list[NativeSession]:
    root = config_dir / "chats"
    if not root.is_dir():
        return []
    sessions: list[NativeSession] = []
    failures = 0
    stores = sorted(root.glob("*/*/store.db"))
    for db in stores:
        sid = db.parent.name
        if not is_session_id(sid):
            continue
        try:
            meta = _cursor_meta(db)
        except (sqlite3.Error, ValueError, UnicodeDecodeError):
            failures += 1
            continue
        name = meta.get("name")
        sessions.append(
            NativeSession(
                session_id=sid,
                title=scrub_secrets(str(name) if isinstance(name, str) else ""),
                cwd=None,
                created_at=_when_ms(meta.get("createdAt")),
                last_activity_at=_mtime(db),
            )
        )
    if stores and failures == len(stores):
        raise StoreUnreadable("none of Cursor's chat stores could be read")
    return sessions


class CursorNativeSessions:
    """``NativeSessionSource`` for Cursor's command-line agent."""

    async def list(
        self, config_dir: pathlib.Path, *, q: str | None, limit: int, position: list[Any] | None
    ) -> SourcePage:
        sessions = await asyncio.to_thread(read_cursor_sessions, config_dir)
        return page_sessions(sessions, q=q, limit=limit, position=position)

    async def rename(self, config_dir: pathlib.Path, session_id: str, title: str) -> None:
        return  # Cursor's command line cannot rename a chat

    async def delete(self, config_dir: pathlib.Path, session_id: str) -> None:
        return  # nor delete one


__all__ = [
    "CursorNativeSessions",
    "DshNativeSessions",
    "OpenCodeNativeSessions",
    "StoreUnreadable",
    "opencode_data_dir",
    "page_sessions",
    "read_cursor_sessions",
    "read_dsh_sessions",
    "read_opencode_sessions",
]
