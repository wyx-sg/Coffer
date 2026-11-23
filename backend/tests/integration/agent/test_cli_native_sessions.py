"""OpenCode, DeepSeek Harness and Cursor sessions are read from the stores the
agents keep (spec agent-registry "List the sessions an agent keeps in its own
store").

The stores are built here in the shapes the real agents write (checked against
OpenCode 1.19.6 and 2.3.2 and DeepSeek Harness 0.2.2-rc.5 in the agent-cli
job); the fallback to Coffer's own conversations is tested with a stand-in
source.
"""

from __future__ import annotations

import json
import os
import pathlib
import sqlite3
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.application.agent.native_session_service import SourcePage
from coffer.application.agent.session_listing_fallback import FallbackSessionSource
from coffer.domain.agent.native_sessions import NativeSession, NativeSessionNotFound
from coffer.infrastructure.agent.cli_native_sessions import (
    CursorNativeSessions,
    DshNativeSessions,
    OpenCodeNativeSessions,
    StoreUnreadable,
    read_cursor_sessions,
    read_dsh_sessions,
    read_opencode_sessions,
)

T0 = 1_795_400_000_000


def _opencode_db(path: pathlib.Path, table: str, rows: list[tuple[Any, ...]]) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            f"CREATE TABLE {table} (id TEXT PRIMARY KEY, project_id TEXT, parent_id TEXT, "
            "directory TEXT, title TEXT, time_created INTEGER, time_updated INTEGER, "
            "time_archived INTEGER)"
        )
        conn.executemany(
            f"INSERT INTO {table} (id, parent_id, directory, title, time_created, time_updated, "
            "time_archived) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    return path


_ROWS = [
    ("ses_old", None, "/work/a", "Fix the build", T0, T0 + 10),
    ("ses_new", None, "/work/b", "Write the docs", T0 + 20, T0 + 30),
    ("ses_child", "ses_new", "/work/b", "subtask", T0 + 21, T0 + 40),
    ("ses_gone", None, "/work/a", "archived", T0, T0 + 50),
]


def _rows(archived: str = "ses_gone") -> list[tuple[Any, ...]]:
    return [(*r, T0 + 60 if r[0] == archived else None) for r in _ROWS]


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="OpenCode's sessions are read from its database, 1.x or 2.x",
)
@pytest.mark.parametrize("table", ["session", "session_v2"])
async def test_opencode_lists_top_level_sessions(tmp_path: pathlib.Path, table: str) -> None:
    data = tmp_path / "share" / "opencode"
    _opencode_db(data / "opencode.db", table, _rows())
    source = OpenCodeNativeSessions(which=lambda _p: None, env=dict, data_dir=lambda: data)

    page = await source.list(tmp_path / "config", q=None, limit=10, position=None)

    assert [s.session_id for s in page.items] == ["ses_new", "ses_old"]
    assert page.items[0].title == "Write the docs"
    assert page.items[0].cwd == "/work/b"
    assert page.items[0].created_at == datetime.fromtimestamp((T0 + 20) / 1000, tz=UTC)
    assert page.total == 2

    first = await source.list(tmp_path, q=None, limit=1, position=None)
    assert [s.session_id for s in first.items] == ["ses_new"]
    rest = await source.list(tmp_path, q=None, limit=1, position=first.next_position)
    assert [s.session_id for s in rest.items] == ["ses_old"] and rest.next_position is None

    found = await source.list(tmp_path, q="BUILD", limit=10, position=None)
    assert [s.session_id for s in found.items] == ["ses_old"]


def test_opencode_without_a_database_has_no_sessions(tmp_path: pathlib.Path) -> None:
    assert read_opencode_sessions(tmp_path / "opencode.db") == []


def test_opencode_database_that_is_not_one_is_unreadable(tmp_path: pathlib.Path) -> None:
    db = tmp_path / "opencode.db"
    db.write_bytes(b"not a database" * 100)
    with pytest.raises(StoreUnreadable):
        read_opencode_sessions(db)


def _fake_opencode(tmp_path: pathlib.Path, rc: int, out: str) -> pathlib.Path:
    script = tmp_path / "opencode"
    record = tmp_path / "argv.json"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        f"json.dump({{'argv': sys.argv[1:], 'cfg': os.environ.get('OPENCODE_CONFIG_DIR')}}, "
        f"open({str(record)!r}, 'w'))\n"
        f"print({out!r})\n"
        f"sys.exit({rc})\n"
    )
    script.chmod(0o755)
    return script


@pytest.mark.acceptance(
    spec="agent-registry", scenario="OpenCode deletes a session through its own command"
)
@pytest.mark.parametrize(("table", "standalone"), [("session", False), ("session_v2", True)])
async def test_opencode_deletes_through_its_command(
    tmp_path: pathlib.Path, table: str, standalone: bool
) -> None:
    data = tmp_path / "share"
    _opencode_db(data / "opencode.db", table, _rows())
    binary = _fake_opencode(tmp_path, 0, "Session ses_old deleted")
    source = OpenCodeNativeSessions(which=lambda _p: str(binary), env=dict, data_dir=lambda: data)

    await source.delete(tmp_path / "cfg", "ses_old")

    seen = json.loads((tmp_path / "argv.json").read_text())
    expected = ["session", "delete", *(["--standalone"] if standalone else []), "ses_old"]
    assert seen["argv"] == expected
    assert seen["cfg"] == str(tmp_path / "cfg")


async def test_opencode_delete_of_an_unknown_session_is_not_found(tmp_path: pathlib.Path) -> None:
    binary = _fake_opencode(tmp_path, 1, "Error: Session not found: ses_x")
    source = OpenCodeNativeSessions(
        which=lambda _p: str(binary), env=dict, data_dir=lambda: tmp_path
    )
    with pytest.raises(NativeSessionNotFound):
        await source.delete(tmp_path, "ses_x")


def _dsh_session(
    home: pathlib.Path, sid: str, *, cwd: str, title: str | None, first: str, created: int
) -> None:
    folder = home / "sessions" / f"-{cwd.replace('/', '-')}-" / sid
    folder.mkdir(parents=True)
    (folder / "session.v4.jsonl.zstd").write_bytes(b"\x28\xb5\x2f\xfd")
    (folder / "session.lock").write_text("")
    cache = home / "storages" / "session_projcache" / "sessions"
    cache.mkdir(parents=True, exist_ok=True)
    rows: dict[str, Any] = {
        "titleInput": {"ver": 3, "seq": 1, "val": {"first": {"seq": 1, "text": first}}},
        "workingDirectory": {"ver": 1, "seq": 1, "val": cwd},
    }
    if title is not None:
        rows["title"] = {"ver": 1, "seq": 9, "val": title}
    record = {"identity": {"formatVersion": 4, "createdAt": created, "cwd": cwd}, "rows": rows}
    (cache / f"{sid}.json").write_text(json.dumps({"version": 7, "record": record}))


@pytest.mark.acceptance(
    spec="agent-registry",
    scenario="DeepSeek Harness's sessions are read from its session folders",
)
async def test_dsh_lists_its_session_folders(tmp_path: pathlib.Path) -> None:
    home = tmp_path / ".dsh"
    _dsh_session(home, "session-a", cwd="/work/a", title="Fix it", first="please", created=T0)
    _dsh_session(home, "session-b", cwd="/work/b", title=None, first="say hi\nmore", created=T0 + 5)
    later = datetime(2030, 1, 1, tzinfo=UTC).timestamp()
    log = next((home / "sessions").glob("*/session-a/session.v4.jsonl.zstd"))
    os.utime(log, (later, later))

    page = await DshNativeSessions().list(home, q=None, limit=10, position=None)

    assert [(s.session_id, s.title, s.cwd) for s in page.items] == [
        ("session-a", "Fix it", "/work/a"),
        ("session-b", "say hi", "/work/b"),
    ]
    assert page.items[0].last_activity_at == datetime.fromtimestamp(later, tz=UTC)
    assert page.items[1].created_at == datetime.fromtimestamp((T0 + 5) / 1000, tz=UTC)


def test_dsh_without_sessions_has_none(tmp_path: pathlib.Path) -> None:
    assert read_dsh_sessions(tmp_path / ".dsh") == []


def _cursor_chat(config: pathlib.Path, chat: str, meta: dict[str, Any] | None) -> pathlib.Path:
    folder = config / "chats" / "0f3c2d" / chat
    folder.mkdir(parents=True)
    db = folder / "store.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("CREATE TABLE blobs (id TEXT PRIMARY KEY, data BLOB)")
        if meta is not None:
            conn.execute("INSERT INTO meta VALUES ('0', ?)", (json.dumps(meta).encode().hex(),))
    return db


@pytest.mark.acceptance(spec="agent-registry", scenario="Cursor's chats are read from their stores")
async def test_cursor_lists_its_chats(tmp_path: pathlib.Path) -> None:
    config = tmp_path / ".cursor"
    chat = "4b7e7a1e-0000-4000-8000-000000000001"
    _cursor_chat(config, chat, {"agentId": chat, "name": "Refactor login", "createdAt": T0})

    page = await CursorNativeSessions().list(config, q=None, limit=10, position=None)

    assert [(s.session_id, s.title) for s in page.items] == [(chat, "Refactor login")]
    assert page.items[0].created_at == datetime.fromtimestamp(T0 / 1000, tz=UTC)
    assert page.items[0].last_activity_at is not None


def test_cursor_stores_none_of_which_can_be_read_are_unreadable(tmp_path: pathlib.Path) -> None:
    config = tmp_path / ".cursor"
    folder = config / "chats" / "h" / "chat-1"
    folder.mkdir(parents=True)
    (folder / "store.db").write_bytes(b"garbage" * 100)
    with pytest.raises(StoreUnreadable):
        read_cursor_sessions(config)


class _Source:
    def __init__(self, page: SourcePage | None = None, error: Exception | None = None) -> None:
        self.page = page or SourcePage(items=[], next_position=None, total=0)
        self.error = error
        self.calls: list[list[Any] | None] = []

    async def list(
        self, config_dir: pathlib.Path, *, q: str | None, limit: int, position: list[Any] | None
    ) -> SourcePage:
        self.calls.append(position)
        if self.error is not None:
            raise self.error
        return self.page

    async def rename(self, config_dir: pathlib.Path, session_id: str, title: str) -> None:
        return

    async def delete(self, config_dir: pathlib.Path, session_id: str) -> None:
        return


def _one(sid: str) -> SourcePage:
    session = NativeSession(
        session_id=sid, title=sid, cwd=None, created_at=None, last_activity_at=None
    )
    return SourcePage(items=[session], next_position=["c2"], total=None)


@pytest.mark.acceptance(
    spec="agent-registry", scenario="an unreadable store lists the conversations Coffer ran"
)
async def test_an_unreadable_store_falls_back_to_coffers_conversations(
    tmp_path: pathlib.Path,
) -> None:
    primary = _Source(error=StoreUnreadable("changed format"))
    fallback = _Source(page=_one("session-coffer"))
    source = FallbackSessionSource(primary, fallback, unreadable=(StoreUnreadable,))

    page = await source.list(tmp_path, q=None, limit=10, position=None)
    assert [s.session_id for s in page.items] == ["session-coffer"]

    # The fallback's next page goes straight back to it.
    await source.list(tmp_path, q=None, limit=10, position=page.next_position)
    assert fallback.calls == [None, ["c2"]]
    assert primary.calls == [None]

    # A later page of the primary's list ends the list.
    stale = await source.list(tmp_path, q=None, limit=10, position=["2030-01-01T00:00:00", "x"])
    assert stale.items == [] and stale.next_position is None


async def test_a_readable_store_is_listed_as_it_is(tmp_path: pathlib.Path) -> None:
    primary = _Source(page=_one("ses_own"))
    fallback = _Source(page=_one("session-coffer"))
    source = FallbackSessionSource(primary, fallback, unreadable=(StoreUnreadable,))
    page = await source.list(tmp_path, q=None, limit=10, position=None)
    assert [s.session_id for s in page.items] == ["ses_own"]
    assert fallback.calls == []
