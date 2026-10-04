"""``POST /api/v1/daemon/restart`` (spec daemon "Restart itself on request").

The successor spawn and the exit are injected (``get_self_restart``), so no
test here starts a process or signals the test runner.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.surfaces.http import daemon_port, daemon_restart_routes
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.daemon_restart_routes import SelfRestart, get_self_restart
from coffer.surfaces.http.dependencies import get_audit_service_optional

_TOKEN = "restart-token"


class _Audit:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    async def record(self, event: str, *, actor: str, details: dict[str, Any]) -> None:
        self.records.append((event, details))


class _Restart:
    """Records what the route asked for, in order."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[str] = []
        self.fail = fail

    def spawn(self) -> int:
        self.calls.append("spawn")
        if self.fail:
            raise OSError("no such file: coffer-daemon")
        return 4242

    def exit(self) -> None:
        self.calls.append("exit")


@pytest.fixture(autouse=True)
def _fresh_state() -> None:
    daemon_restart_routes.reset_restart_state()


def _app(restart: _Restart, audit: _Audit) -> FastAPI:
    set_active_token(_TOKEN)
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(daemon_restart_routes.router)
    app.dependency_overrides[get_self_restart] = lambda: SelfRestart(
        spawn_successor=restart.spawn, exit_self=restart.exit
    )
    app.dependency_overrides[get_audit_service_optional] = lambda: audit
    return app


async def _client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": _TOKEN}
    ) as c:
        yield c


@pytest.mark.acceptance(
    spec="daemon", scenario="a restart asked from the web ui starts a successor"
)
async def test_restart_starts_the_successor_then_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(daemon_restart_routes.bootstrap, "planned_port", lambda: 8123)
    restart, audit = _Restart(), _Audit()
    async for c in _client(_app(restart, audit)):
        r = await c.post("/api/v1/daemon/restart")
    assert r.status_code == 202
    assert r.json() == {"port": 8123}
    # The successor first; the exit only after the answer went out.
    assert restart.calls == ["spawn", "exit"]
    assert audit.records == [("daemon_restarted", {"port": 8123, "successor_pid": 4242})]


async def test_a_second_press_does_not_start_a_second_successor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(daemon_restart_routes.bootstrap, "planned_port", lambda: None)
    monkeypatch.setattr(daemon_port, "_PORT", 38470)
    restart, audit = _Restart(), _Audit()
    async for c in _client(_app(restart, audit)):
        first = await c.post("/api/v1/daemon/restart")
        second = await c.post("/api/v1/daemon/restart")
    # A test port range: the successor binds where this daemon answers.
    assert first.json() == second.json() == {"port": 38470}
    assert restart.calls == ["spawn", "exit"]
    assert len(audit.records) == 1


async def test_two_simultaneous_presses_start_one_successor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The claim is taken before the (slow) spawn is awaited, so requests that
    arrive while it runs do not each start a successor."""
    import asyncio
    import threading

    monkeypatch.setattr(daemon_restart_routes.bootstrap, "planned_port", lambda: 38470)
    gate = threading.Event()
    restart, audit = _Restart(), _Audit()

    def _slow_spawn() -> int:
        restart.calls.append("spawn")
        gate.wait(2)
        return 4242

    app = _app(restart, audit)
    app.dependency_overrides[get_self_restart] = lambda: SelfRestart(
        spawn_successor=_slow_spawn, exit_self=restart.exit
    )
    async for c in _client(app):
        first = asyncio.ensure_future(c.post("/api/v1/daemon/restart"))
        await asyncio.sleep(0.2)  # the first is now inside the spawn
        second = await c.post("/api/v1/daemon/restart")
        gate.set()
        await first
    assert second.status_code == 202
    assert restart.calls.count("spawn") == 1
    assert len(audit.records) == 1


@pytest.mark.acceptance(
    spec="daemon", scenario="a successor that cannot start leaves the daemon serving"
)
async def test_a_successor_that_cannot_start_leaves_this_daemon_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(daemon_restart_routes.bootstrap, "planned_port", lambda: 38470)
    restart, audit = _Restart(fail=True), _Audit()
    async for c in _client(_app(restart, audit)):
        r = await c.post("/api/v1/daemon/restart")
    assert r.status_code == 500
    assert restart.calls == ["spawn"]  # no exit
    assert audit.records == []


async def test_restart_needs_the_token() -> None:
    restart, audit = _Restart(), _Audit()
    async for c in _client(_app(restart, audit)):
        r = await c.post("/api/v1/daemon/restart", headers={"X-Coffer-Token": "wrong"})
    assert r.status_code == 401
    assert restart.calls == []
