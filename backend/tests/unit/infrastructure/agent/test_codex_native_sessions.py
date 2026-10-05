"""``CodexNativeSessions`` lists and changes threads through ``codex app-server``.

No ``codex`` binary is spawned: the injected session factory hands back a real
``CodexRpcClient`` wired to a scripted JSON-RPC peer over in-memory pipes, so
the handshake and each thread call run against the production RPC client.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import pathlib
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from coffer.domain.agent.native_sessions import NativeSessionNotFound
from coffer.domain.errors import UpstreamTimeout, UpstreamUnavailable
from coffer.infrastructure.agent.codex_native_sessions import CodexNativeSessions
from tests.unit.infrastructure.agent.test_codex_rpc_models import _FakeSession, _Pipe

Handler = Callable[[dict[str, Any]], dict[str, Any]]


class _ScriptedPeer:
    """Answers each method with the handler registered for it; a handler may
    raise ``_RefusedError`` to answer with a JSON-RPC error, and a method with no
    handler is left unanswered (the caller must time out)."""

    def __init__(self, handlers: dict[str, Handler]) -> None:
        self.to_server = _Pipe()
        self.to_client = _Pipe()
        self.handlers = handlers
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while True:
            raw = await self.to_server.readline()
            frame = json.loads(raw.decode("utf-8"))
            if "id" not in frame:
                continue
            method, params = frame["method"], frame.get("params") or {}
            self.requests.append((method, params))
            if method == "initialize":
                reply: dict[str, Any] = {"result": {"userAgent": "codex-test"}}
            elif method in self.handlers:
                try:
                    reply = {"result": self.handlers[method](params)}
                except _RefusedError as refusal:
                    reply = {"error": {"code": -32600, "message": str(refusal)}}
            else:
                continue
            reply.update({"jsonrpc": "2.0", "id": frame["id"]})
            self.to_client.write((json.dumps(reply) + "\n").encode("utf-8"))


class _RefusedError(Exception):
    pass


def _thread(ident: str, **extra: Any) -> dict[str, Any]:
    thread: dict[str, Any] = {
        "id": ident,
        "name": None,
        "preview": f"preview of {ident}",
        "cwd": "/work/repo",
        "createdAt": 1_780_000_000,
        "updatedAt": 1_780_000_100,
    }
    thread.update(extra)
    return thread


def _source(
    peer: _ScriptedPeer, envs: list[dict[str, str] | None] | None = None
) -> CodexNativeSessions:
    def make(cwd: str, env: dict[str, str] | None) -> _FakeSession:
        if envs is not None:
            envs.append(env)
        return _FakeSession(peer, cwd)  # type: ignore[arg-type]

    return CodexNativeSessions(make, timeout=0.5)


@pytest.fixture
def home(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


@pytest.mark.acceptance(
    spec="agent-registry/codex", scenario="list Codex sessions through thread/list"
)
async def test_threads_are_listed_with_the_servers_own_cursor(home: pathlib.Path) -> None:
    peer = _ScriptedPeer(
        {
            "thread/list": lambda p: {
                "data": [
                    _thread("t1", name="Named", preview="ignored"),
                    _thread("t2", preview="  sk-abcdefghijklmnopqrstuvwx  "),
                ],
                "nextCursor": "after-t2",
            }
        }
    )

    page = await _source(peer).list(home / ".codex", q="auth", limit=2, position=["c0"])

    assert [(s.session_id, s.title) for s in page.items] == [
        ("t1", "Named"),
        ("t2", "[redacted]"),
    ]
    assert page.items[0].cwd == "/work/repo"
    assert page.items[0].created_at == datetime.fromtimestamp(1_780_000_000, tz=UTC)
    assert page.items[0].last_activity_at == datetime.fromtimestamp(1_780_000_100, tz=UTC)
    assert page.next_position == ["after-t2"]
    assert page.total is None
    methods = [m for m, _ in peer.requests]
    assert methods == ["initialize", "thread/list"]
    assert peer.requests[1][1] == {
        "limit": 2,
        "cursor": "c0",
        "searchTerm": "auth",
        "sortKey": "updated_at",
        "sourceKinds": ["cli", "vscode", "exec", "appServer"],
    }


async def test_the_last_page_has_no_token_and_no_search_is_sent(home: pathlib.Path) -> None:
    peer = _ScriptedPeer({"thread/list": lambda p: {"data": [_thread("t1")], "nextCursor": None}})

    page = await _source(peer).list(home / ".codex", q=None, limit=10, position=None)

    assert page.next_position is None
    assert "searchTerm" not in peer.requests[-1][1]
    assert "cursor" not in peer.requests[-1][1]


@pytest.mark.acceptance(
    spec="agent-registry/codex", scenario="rename and delete go through the app-server"
)
async def test_rename_and_delete_call_the_thread_methods(home: pathlib.Path) -> None:
    peer = _ScriptedPeer({"thread/name/set": lambda p: {}, "thread/delete": lambda p: {}})
    source = _source(peer)

    await source.rename(home / ".codex", "t1", "New name")
    await source.delete(home / ".codex", "t1")

    assert ("thread/name/set", {"threadId": "t1", "name": "New name"}) in peer.requests
    assert ("thread/delete", {"threadId": "t1"}) in peer.requests


async def test_an_unknown_thread_is_not_found(home: pathlib.Path) -> None:
    def refuse(p: dict[str, Any]) -> dict[str, Any]:
        raise _RefusedError("thread not found: t9")

    peer = _ScriptedPeer({"thread/delete": refuse})

    with pytest.raises(NativeSessionNotFound):
        await _source(peer).delete(home / ".codex", "t9")


@pytest.mark.acceptance(
    spec="agent-registry/codex",
    scenario="ask the app-server of the agent's own Codex home",
)
async def test_a_custom_config_dir_runs_under_its_own_codex_home(home: pathlib.Path) -> None:
    custom = home / "work-codex"
    custom.mkdir()
    peer = _ScriptedPeer({"thread/list": lambda p: {"data": []}})
    envs: list[dict[str, str] | None] = []

    await _source(peer, envs).list(custom, q=None, limit=5, position=None)
    await _source(peer, envs).list(home / ".codex", q=None, limit=5, position=None)

    assert envs[0] is not None and envs[0]["CODEX_HOME"] == str(custom)
    assert envs[1] is None


async def test_a_missing_codex_is_unavailable_and_a_silent_one_times_out(
    home: pathlib.Path,
) -> None:
    def absent(cwd: str, env: dict[str, str] | None) -> Any:
        raise RuntimeError("codex binary not found on PATH")

    with pytest.raises(UpstreamUnavailable):
        await CodexNativeSessions(absent).list(home, q=None, limit=5, position=None)

    peer = _ScriptedPeer({})
    session_holder: list[_FakeSession] = []

    def make(cwd: str, env: dict[str, str] | None) -> _FakeSession:
        session_holder.append(_FakeSession(peer, cwd))  # type: ignore[arg-type]
        return session_holder[0]

    with pytest.raises(UpstreamTimeout):
        await CodexNativeSessions(make, timeout=0.2).list(home, q=None, limit=5, position=None)
    assert session_holder[0].closed
