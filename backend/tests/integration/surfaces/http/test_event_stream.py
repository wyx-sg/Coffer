"""``GET /api/v1/events`` through the real composition root (spec
resource-framework "Announce every change on one daemon-wide event stream").

Each test boots the whole daemon in the test's own event loop (the lifespan
wires the broker into the resource repository's hint sink and starts the
attention watcher), writes through the REST routes, and reads the live stream
at the ASGI level (:mod:`._sse`), because no HTTP test client returns a
response that never ends.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.surfaces.http import event_wiring
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.event_dependencies import get_event_broker, get_heartbeat_seconds
from tests.integration.surfaces.http._sse import SseEvent, SseStream

pytestmark = pytest.mark.asyncio

_TOKEN = "test-token-events"
_AUTH = {"X-Coffer-Token": _TOKEN}
_ENVELOPE_FIELDS = {"seq", "kind", "id", "rev", "op"}


@dataclass
class _Daemon:
    app: FastAPI
    client: AsyncClient

    def stream(self, headers: dict[str, str] | None = None) -> SseStream:
        return SseStream(self.app, "/api/v1/events", {**_AUTH, **(headers or {})})

    async def register(self, name: str, command: str = "/bin/echo") -> dict[str, Any]:
        r = await self.client.post(
            "/api/v1/resources",
            json={
                "kind": "mcp_server",
                "name": name,
                "config": {"transport": {"type": "stdio", "command": command}},
            },
        )
        assert r.status_code == 201, r.text
        body: dict[str, Any] = r.json()
        return body


async def _boot(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Daemon]:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    app = create_app()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app), base_url="http://localhost", headers=_AUTH) as c,
    ):
        set_active_token(_TOKEN)  # after startup, so it wins over daemon.json
        yield _Daemon(app, c)


@pytest.fixture
async def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Daemon]:
    async for d in _boot(tmp_path, monkeypatch):
        yield d


async def _next_change(stream: SseStream, *, kind: str | None = None) -> SseEvent:
    """The next ``change`` event (of ``kind``, when given)."""
    while True:
        event = await stream.next_event()
        if event.event == "change" and (kind is None or event.data["kind"] == kind):
            return event


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a resource write is announced as an invalidation hint"
)
async def test_a_disable_then_a_delete_are_two_consecutive_hints(daemon: _Daemon) -> None:
    server = await daemon.register("srv")
    stream = daemon.stream()
    assert await stream.open() == 200
    try:
        r = await daemon.client.post(f"/api/v1/resources/{server['uid']}/disable")
        assert r.status_code == 200, r.text
        # The wire resource carries no revision; the row does.
        disabled_rev = (await get_resource_service().get(server["uid"])).rev
        r = await daemon.client.delete(f"/api/v1/resources/{server['uid']}")
        assert r.status_code == 204, r.text

        upsert = await _next_change(stream, kind="mcp_server")
        delete = await _next_change(stream, kind="mcp_server")
    finally:
        await stream.close()

    assert upsert.data == {
        "seq": upsert.data["seq"],
        "kind": "mcp_server",
        "id": server["uid"],
        "rev": disabled_rev,
        "op": "upsert",
    }
    assert delete.data == {
        "seq": upsert.data["seq"] + 1,
        "kind": "mcp_server",
        "id": server["uid"],
        "rev": disabled_rev + 1,
        "op": "delete",
    }
    # The SSE id names this run and the seq; nothing of the resource beyond
    # kind/uid/rev travels.
    run = get_event_broker().run
    assert (upsert.id, delete.id) == (f"{run}.{upsert.data['seq']}", f"{run}.{delete.data['seq']}")
    assert set(upsert.data) == set(delete.data) == _ENVELOPE_FIELDS


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a reconnecting client resumes after the last event it saw"
)
async def test_reconnecting_with_last_event_id_replays_exactly_what_was_missed(
    daemon: _Daemon,
) -> None:
    first = daemon.stream()
    await first.open()
    await daemon.register("seen")
    last_seen = await _next_change(first, kind="mcp_server")
    await first.close()

    missed = [await daemon.register("missed-1"), await daemon.register("missed-2")]

    assert last_seen.id is not None
    second = daemon.stream({"Last-Event-ID": last_seen.id})
    await second.open()
    try:
        replayed = [await second.next_event(), await second.next_event()]
        await daemon.register("live")
        live = await _next_change(second, kind="mcp_server")
    finally:
        await second.close()

    n = last_seen.data["seq"]
    assert [(e.event, e.data["seq"], e.data["id"]) for e in replayed] == [
        ("change", n + 1, missed[0]["uid"]),
        ("change", n + 2, missed[1]["uid"]),
    ]
    assert live.data["seq"] == n + 3


@pytest.mark.acceptance(
    spec="resource-framework", scenario="a client the buffer cannot cover is told to resync"
)
@pytest.mark.parametrize(
    "gap", ["older_than_the_buffer", "never_issued", "an_earlier_run", "not_an_id"]
)
async def test_an_uncoverable_last_event_id_gets_resync_then_live_changes(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, gap: str
) -> None:
    monkeypatch.setattr(event_wiring, "BUFFER_SIZE", 2)
    async for daemon in _boot(tmp_path, monkeypatch):
        first = await daemon.register("first")
        for i in range(3):  # more writes than the buffer holds
            await daemon.register(f"later-{i}")
        broker = get_event_broker()
        # The first write has already left the buffer.
        assert first["uid"] not in {e.id for e in broker.buffered}
        run = broker.run
        last_event_id = {
            "older_than_the_buffer": f"{run}.{broker.buffered[0].seq - 2}",
            "never_issued": f"{run}.{broker.head + 1000}",
            # Every run numbers from 1, so a seq this run HAS issued, under
            # another run's name, is still one this run never issued.
            "an_earlier_run": f"0badc0ffee00.{broker.buffered[-1].seq}",
            "not_an_id": "yesterday",
        }[gap]

        stream = daemon.stream({"Last-Event-ID": last_event_id})
        await stream.open()
        try:
            opening = await stream.next_event()
            live_server = await daemon.register("live")
            live = await _next_change(stream, kind="mcp_server")
        finally:
            await stream.close()

        assert opening.event == "resync"
        assert opening.data == {"seq": live.data["seq"] - 1}
        assert live.data["id"] == live_server["uid"]


@pytest.mark.acceptance(
    spec="resource-framework", scenario="an attention change is announced on the event stream"
)
async def test_an_item_joining_the_attention_list_is_one_attention_hint(daemon: _Daemon) -> None:
    r = await daemon.client.get("/api/v1/attention")
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []
    stream = daemon.stream()
    await stream.open()
    try:
        # A stdio server whose launcher does not resolve here needs a person.
        await daemon.register("orphan", command="coffer-no-such-launcher")
        announced = await _next_change(stream, kind="attention")
    finally:
        await stream.close()

    assert announced.data == {
        "seq": announced.data["seq"],
        "kind": "attention",
        "id": None,
        "rev": None,
        "op": "upsert",
    }
    r = await daemon.client.get("/api/v1/attention")
    assert [i["reason_code"] for i in r.json()["items"]] == ["mcp_missing_launcher"]


@pytest.mark.acceptance(
    spec="resource-framework", scenario="an idle event stream carries heartbeats"
)
async def test_an_idle_stream_sends_heartbeats_with_the_head_seq(daemon: _Daemon) -> None:
    daemon.app.dependency_overrides[get_heartbeat_seconds] = lambda: 0.1
    head = get_event_broker().head
    stream = daemon.stream()
    await stream.open()
    try:
        beats = [await stream.next_event(timeout=2), await stream.next_event(timeout=2)]
    finally:
        await stream.close()
        daemon.app.dependency_overrides.clear()

    assert [(b.event, b.data) for b in beats] == [
        ("heartbeat", {"seq": head}),
        ("heartbeat", {"seq": head}),
    ]


@pytest.mark.acceptance(spec="resource-framework", scenario="the event stream requires the token")
async def test_the_stream_without_the_token_is_refused_401(daemon: _Daemon) -> None:
    subscribers = get_event_broker().subscriber_count
    stream = SseStream(daemon.app, "/api/v1/events", {})
    assert await stream.open() == 401
    body = await stream.finished_body()
    assert b'"UNAUTHENTICATED"' in body
    assert get_event_broker().subscriber_count == subscribers  # no stream was opened
