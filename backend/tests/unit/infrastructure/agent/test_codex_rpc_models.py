"""Unit tests for ``CodexRpcModelDiscovery``.

No ``codex`` binary is spawned. The adapter's injected session factory hands it
a real ``CodexRpcClient`` wired to a scripted JSON-RPC peer over in-memory
NDJSON pipes — the same seam ``FakeCodexAppServer`` uses in the app-server
adapter's tests — so the handshake, the ``model/list`` call and the pagination
loop run against the production RPC client, with only the process replaced.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import pathlib
from typing import Any

from coffer.infrastructure.agent.codex_rpc_models import CodexRpcModelDiscovery
from coffer.infrastructure.chat.codex_jsonrpc import CodexRpcClient


class _Pipe:
    """An in-memory NDJSON pipe: one side writes, the other reads."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[bytes] = asyncio.Queue()

    def write(self, data: bytes) -> None:
        self._queue.put_nowait(data)

    async def drain(self) -> None:
        return None

    async def readline(self) -> bytes:
        return await self._queue.get()


class FakeCodexPeer:
    """A scripted ``codex app-server`` peer that answers ``model/list``.

    ``pages`` is the sequence of ``model/list`` results to hand back, one per
    call; the last one is repeated if the adapter somehow asks again.
    """

    def __init__(self, pages: list[dict[str, Any]], *, answer_model_list: bool = True) -> None:
        self.to_server = _Pipe()
        self.to_client = _Pipe()
        self._pages = pages
        self._answer_model_list = answer_model_list
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
        calls = 0
        while True:
            raw = await self.to_server.readline()
            if not raw:
                return
            frame = json.loads(raw.decode("utf-8"))
            method = frame.get("method")
            if "id" not in frame:
                continue  # a notification (``initialized``) — nothing to answer
            self.requests.append((method, frame.get("params") or {}))
            if method == "model/list":
                if not self._answer_model_list:
                    continue  # deliberately silent — the adapter must time out
                page = self._pages[min(calls, len(self._pages) - 1)]
                calls += 1
                await self._send({"jsonrpc": "2.0", "id": frame["id"], "result": page})
            else:
                await self._send({"jsonrpc": "2.0", "id": frame["id"], "result": {}})

    async def _send(self, obj: dict[str, Any]) -> None:
        self.to_client.write((json.dumps(obj) + "\n").encode("utf-8"))


class _FakeSession:
    """A started session whose ``rpc`` talks to a :class:`FakeCodexPeer`."""

    def __init__(self, peer: FakeCodexPeer, cwd: str) -> None:
        self.peer = peer
        self.cwd = cwd
        self.closed = False
        self._rpc = CodexRpcClient(peer.to_client, peer.to_server)

    @property
    def rpc(self) -> CodexRpcClient:
        return self._rpc

    async def start(self) -> None:
        self.peer.start()
        self._rpc.start()

    async def close(self) -> None:
        self.closed = True
        await self._rpc.close()
        await self.peer.stop()


def _model(model_id: str, **extra: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "id": model_id,
        "model": model_id,
        "displayName": model_id.upper(),
        "description": f"about {model_id}",
        "hidden": False,
    }
    entry.update(extra)
    return entry


def _factory(peer: FakeCodexPeer) -> tuple[Any, list[_FakeSession]]:
    """A session factory that records the sessions it built."""
    built: list[_FakeSession] = []

    def make(cwd: str, env: dict[str, str] | None) -> _FakeSession:
        session = _FakeSession(peer, cwd)
        built.append(session)
        return session

    return make, built


async def test_model_list_becomes_the_catalogue() -> None:
    peer = FakeCodexPeer([{"data": [_model("gpt-x"), _model("gpt-y")], "nextCursor": None}])
    make, built = _factory(peer)

    models = await CodexRpcModelDiscovery(make).discover(agent_key="codex", config_dir=None)

    assert [(m.id, m.label, m.description, m.source) for m in models] == [
        ("gpt-x", "GPT-X", "about gpt-x", "discovered"),
        ("gpt-y", "GPT-Y", "about gpt-y", "discovered"),
    ]
    # The handshake the app-server protocol requires ran before the list call.
    assert [method for method, _ in peer.requests] == ["initialize", "model/list"]
    # The process never outlives the probe.
    assert built[0].closed is True


async def test_hidden_models_are_not_offered() -> None:
    peer = FakeCodexPeer(
        [{"data": [_model("shown"), _model("internal", hidden=True)], "nextCursor": None}]
    )
    make, _ = _factory(peer)

    models = await CodexRpcModelDiscovery(make).discover(agent_key="codex", config_dir=None)

    assert [m.id for m in models] == ["shown"]


async def test_a_next_cursor_is_followed() -> None:
    peer = FakeCodexPeer(
        [
            {"data": [_model("page-1")], "nextCursor": "c2"},
            {"data": [_model("page-2")], "nextCursor": None},
        ]
    )
    make, _ = _factory(peer)

    models = await CodexRpcModelDiscovery(make).discover(agent_key="codex", config_dir=None)

    assert [m.id for m in models] == ["page-1", "page-2"]
    # The cursor goes back as a request param, not as a fresh unpaged call.
    assert [params for method, params in peer.requests if method == "model/list"] == [
        {},
        {"cursor": "c2"},
    ]


async def test_a_peer_that_never_answers_times_out_to_empty() -> None:
    """A wedged CLI must not hold a model picker open."""
    peer = FakeCodexPeer([], answer_model_list=False)
    make, built = _factory(peer)

    models = await CodexRpcModelDiscovery(make, timeout=0.2).discover(
        agent_key="codex", config_dir=None
    )

    assert models == []
    assert built[0].closed is True


async def test_a_factory_that_raises_means_codex_is_not_installed() -> None:
    def make(cwd: str, env: dict[str, str] | None) -> Any:
        raise RuntimeError("codex binary not found on PATH")

    assert await CodexRpcModelDiscovery(make).discover(agent_key="codex", config_dir=None) == []


async def test_malformed_payloads_are_skipped_not_fatal() -> None:
    peer = FakeCodexPeer(
        [
            {
                "data": [
                    "not an object",
                    {"model": "fallback-id"},  # no ``id`` — ``model`` stands in
                    {"id": "   "},  # blank — dropped
                    {"id": "ok", "displayName": 7, "description": None},
                ],
                "nextCursor": 12,  # not a string — pagination stops
            }
        ]
    )
    make, _ = _factory(peer)

    models = await CodexRpcModelDiscovery(make).discover(agent_key="codex", config_dir=None)

    assert [(m.id, m.label, m.description) for m in models] == [
        ("fallback-id", "", ""),
        ("ok", "", ""),
    ]


async def test_the_probe_is_cached_for_the_ttl() -> None:
    peer = FakeCodexPeer([{"data": [_model("gpt-x")], "nextCursor": None}])
    make, built = _factory(peer)
    now = [100.0]
    discovery = CodexRpcModelDiscovery(make, ttl=60.0, clock=lambda: now[0])

    await discovery.discover(agent_key="codex", config_dir=None)
    now[0] = 150.0
    await discovery.discover(agent_key="codex", config_dir=None)
    assert len(built) == 1, "spawning a CLI per request is the bug this cache exists to stop"

    now[0] = 200.0  # past the TTL
    await discovery.discover(agent_key="codex", config_dir=None)
    assert len(built) == 2


async def test_an_empty_answer_is_not_cached() -> None:
    """A Codex that is missing or logged out is a state the user fixes in
    seconds; holding its emptiness for the TTL would leave the picker blank
    long after they had fixed it."""
    peer = FakeCodexPeer([{"data": [], "nextCursor": None}])
    make, built = _factory(peer)
    now = [100.0]
    discovery = CodexRpcModelDiscovery(make, ttl=60.0, clock=lambda: now[0])

    assert await discovery.discover(agent_key="codex", config_dir=None) == []
    now[0] = 110.0  # well inside the TTL
    assert await discovery.discover(agent_key="codex", config_dir=None) == []
    assert len(built) == 2, "an empty probe must be retried, not remembered"


async def test_another_agent_type_never_spawns_anything(tmp_path: pathlib.Path) -> None:
    peer = FakeCodexPeer([{"data": [_model("gpt-x")], "nextCursor": None}])
    make, built = _factory(peer)

    models = await CodexRpcModelDiscovery(make).discover(
        agent_key="claude_code", config_dir=tmp_path
    )

    assert models == []
    assert built == []


async def test_the_probe_starts_in_a_directory_that_exists(tmp_path: pathlib.Path) -> None:
    """``model/list`` needs no project context, but the process still has to be
    spawned somewhere real — the agent's config dir when there is one."""
    peer = FakeCodexPeer([{"data": [], "nextCursor": None}])
    make, built = _factory(peer)

    await CodexRpcModelDiscovery(make).discover(agent_key="codex", config_dir=tmp_path)
    assert built[0].cwd == str(tmp_path)

    peer2 = FakeCodexPeer([{"data": [], "nextCursor": None}])
    make2, built2 = _factory(peer2)
    await CodexRpcModelDiscovery(make2).discover(
        agent_key="codex", config_dir=tmp_path / "does-not-exist"
    )
    assert built2[0].cwd == str(pathlib.Path.home())
