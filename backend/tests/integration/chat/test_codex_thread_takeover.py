"""A Codex thread another Codex process holds is taken over, then resumed.

Spec chat "Take over a session open elsewhere". The turn's own app-server is the
scripted fake from ``test_codex_app_server_agent``; Codex's shared background
app-server is a small WebSocket server on a Unix socket speaking the few
JSON-RPC methods the release uses.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import shutil
import tempfile
from collections.abc import AsyncIterator
from typing import Any

import pytest
from websockets.asyncio.server import ServerConnection, unix_serve

from coffer.domain.chat.events import SESSION_IN_USE, SESSION_IN_USE_MESSAGE, TurnDone, TurnError
from coffer.infrastructure.chat.codex_agent import CodexAppServerAdapter
from coffer.infrastructure.chat.codex_thread_release import (
    CodexThreadRelease,
    is_terminal_codex,
    lock_holders,
    release_in_daemon,
)
from coffer.infrastructure.chat.session_takeover import ProcessInfo

from .test_codex_app_server_agent import FakeCodexAppServer, _basic_frames, _Factory

THREAD = "thread-1"
_ACTIVE_WRITER = f"thread {THREAD} already has an active writer"


class _Release:
    """Frees the fake server's thread when called, as a real release would."""

    def __init__(self, server: FakeCodexAppServer | None, *, frees: bool = True) -> None:
        self.server = server
        self.frees = frees
        self.asked: list[str] = []

    async def __call__(self, thread_id: str) -> bool:
        self.asked.append(thread_id)
        if self.frees and self.server is not None:
            self.server._fail_methods.discard("thread/resume")
        return self.frees


def _held_server() -> FakeCodexAppServer:
    return FakeCodexAppServer(
        frames=_basic_frames(),
        fail_methods={"thread/resume"},
        fail_messages={"thread/resume": _ACTIVE_WRITER},
    )


async def _run(server: FakeCodexAppServer, release: _Release, saved: list[str]) -> list[Any]:
    async def on_session(sid: str) -> None:
        saved.append(sid)

    adapter = CodexAppServerAdapter(
        cwd="/tmp",
        resume_session=THREAD,
        extra={},
        session_factory=_Factory(server),
        on_session=on_session,
        release_thread=release,
    )
    stream = await adapter.run_turn("hi")
    return [ev async for ev in stream]


@pytest.mark.acceptance(
    spec="chat", scenario="a Codex session held by Codex's background app-server is taken over"
)
async def test_a_held_thread_is_released_and_resumed() -> None:
    server = _held_server()
    release = _Release(server)
    saved: list[str] = []

    events = await asyncio.wait_for(_run(server, release, saved), timeout=5)

    assert release.asked == [THREAD]
    assert isinstance(events[-1], TurnDone)
    methods = [m for m, _ in server.requests]
    assert methods.count("thread/resume") == 2
    assert "thread/start" not in methods  # the same thread, not a fork


async def test_a_thread_that_cannot_be_released_is_refused() -> None:
    server = _held_server()
    release = _Release(server, frees=False)

    events = await asyncio.wait_for(_run(server, release, []), timeout=5)

    assert release.asked == [THREAD]
    assert events[-1] == TurnError(code=SESSION_IN_USE, message=SESSION_IN_USE_MESSAGE)
    assert [m for m, _ in server.requests].count("thread/resume") == 1


# --- Codex's shared background app-server ------------------------------------


class _Daemon:
    """The control socket of ``codex app-server --managed-daemon``, in brief."""

    def __init__(self, *, loaded: set[str], running_turn: str | None, unload_after: float | None):
        self.loaded = loaded
        self.running_turn = running_turn
        self.unload_after = unload_after  # None: another client keeps it loaded
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def handle(self, ws: ServerConnection) -> None:
        async for raw in ws:
            frame = json.loads(raw)
            if "id" not in frame:
                continue
            method, params = frame["method"], frame.get("params") or {}
            self.calls.append((method, params))
            result: dict[str, Any] = {}
            if method == "thread/loaded/list":
                result = {"data": sorted(self.loaded), "nextCursor": None}
            elif method == "thread/resume":
                status = "inProgress" if self.running_turn else "completed"
                turns = [{"id": self.running_turn or "turn-0", "status": status, "items": []}]
                result = {"thread": {"id": params["threadId"], "turns": turns}}
            elif method == "turn/interrupt":
                self.running_turn = None
            elif method == "thread/unsubscribe":
                result = {"status": "unsubscribed"}
                if self.unload_after is not None:
                    asyncio.get_running_loop().call_later(
                        self.unload_after, self.loaded.discard, params["threadId"]
                    )
            await ws.send(json.dumps({"id": frame["id"], "result": result}))


@pytest.fixture
async def codex_home() -> AsyncIterator[pathlib.Path]:
    # A short path: a Unix socket's path is capped near 104 bytes.
    home = pathlib.Path(tempfile.mkdtemp(prefix="cx", dir="/tmp"))
    (home / "app-server-control").mkdir()
    yield home
    shutil.rmtree(home, ignore_errors=True)


def _socket(home: pathlib.Path) -> pathlib.Path:
    return home / "app-server-control" / "app-server-control.sock"


@pytest.mark.acceptance(
    spec="chat", scenario="a Codex session held by Codex's background app-server is taken over"
)
async def test_the_daemon_interrupts_unsubscribes_and_unloads_the_thread(
    codex_home: pathlib.Path,
) -> None:
    daemon = _Daemon(loaded={THREAD}, running_turn="turn-9", unload_after=0.2)
    async with unix_serve(daemon.handle, str(_socket(codex_home))):
        released = await CodexThreadRelease(codex_home, unload_timeout=5)(THREAD)

    assert released is True
    methods = [m for m, _ in daemon.calls]
    assert methods[:3] == ["initialize", "thread/loaded/list", "thread/resume"]
    assert ("turn/interrupt", {"threadId": THREAD, "turnId": "turn-9"}) in daemon.calls
    assert ("thread/unsubscribe", {"threadId": THREAD}) in daemon.calls
    assert THREAD not in daemon.loaded


@pytest.mark.acceptance(spec="chat", scenario="a session Coffer cannot take over refuses the turn")
async def test_a_thread_another_client_keeps_loaded_is_not_released(
    codex_home: pathlib.Path,
) -> None:
    daemon = _Daemon(loaded={THREAD}, running_turn=None, unload_after=None)
    async with unix_serve(daemon.handle, str(_socket(codex_home))):
        released = await release_in_daemon(_socket(codex_home), THREAD, unload_timeout=0.5)

    assert released is False
    assert "turn/interrupt" not in [m for m, _ in daemon.calls]


async def test_a_daemon_without_the_thread_leaves_it_to_the_lock_holder_search(
    codex_home: pathlib.Path,
) -> None:
    daemon = _Daemon(loaded={"another"}, running_turn=None, unload_after=0)
    async with unix_serve(daemon.handle, str(_socket(codex_home))):
        released = await release_in_daemon(_socket(codex_home), THREAD)

    assert released is None
    assert "thread/resume" not in [m for m, _ in daemon.calls]


async def test_no_daemon_socket_means_no_daemon(codex_home: pathlib.Path) -> None:
    assert await release_in_daemon(_socket(codex_home), THREAD) is None


# --- a terminal codex with its own embedded app-server -----------------------


def test_only_a_terminal_codex_counts_as_one() -> None:
    assert is_terminal_codex(("/opt/homebrew/bin/codex", "resume", THREAD))
    assert is_terminal_codex(("node", "/usr/local/bin/codex"))
    assert not is_terminal_codex(("codex", "app-server", "--managed-daemon"))
    assert not is_terminal_codex(("/Applications/Codex.app/Contents/Resources/codex", "app-server"))
    assert not is_terminal_codex(("vim", "codex-notes.md"))


def test_the_lock_holder_is_found_by_its_open_files() -> None:
    lock = pathlib.Path("/home/u/.codex/thread-writer-locks") / f"{THREAD}.lock"
    processes = [
        ProcessInfo(100, 1, ("coffer-daemon",)),
        ProcessInfo(101, 100, ("codex", "app-server")),  # Coffer's own turn
        ProcessInfo(500, 1, ("codex",)),
        ProcessInfo(501, 1, ("codex", "resume", "other")),
        ProcessInfo(502, 1, ("python", "x.py")),
    ]
    files = {101: {str(lock)}, 500: {str(lock)}, 501: set(), 502: {str(lock)}}

    holders = lock_holders(
        lock, processes=processes, own_pid=100, open_paths=lambda pid: files[pid]
    )

    assert holders == [(500, ("codex",))]
