"""The Host and Origin guard.

See spec daemon "Refuse a request whose Host or Origin is not the daemon's own".

The daemon's served index.html carries the live API token, so a DNS-rebound
page — one on ``evil.example`` whose hostname resolves to 127.0.0.1, which the
browser therefore treats as same-origin — could otherwise fetch ``/`` and read
the token out of the body. Rebinding does not change the ``Host`` header, so
refusing every authority but the daemon's own closes it. A page on another
site that cannot read the answer can still *send* a request; the Origin check
refuses that, on every surface, while a client that sends no Origin (the CLI,
the shim, an agent's MCP client) goes on to the token check.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocket, WebSocketDisconnect

from coffer.surfaces.http import host_guard
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_PORT = 8000
_BASE = f"http://127.0.0.1:{_PORT}"
_EVIL = "https://evil.example"


@pytest.fixture(autouse=True)
def _enforce(monkeypatch: pytest.MonkeyPatch) -> None:
    """The suite-wide ``COFFER_ALLOWED_HOSTS=*`` escape hatch is off in here,
    and no developer opt-in leaks in from the environment."""
    monkeypatch.delenv("COFFER_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("COFFER_DEV_CORS", raising=False)
    monkeypatch.delenv("COFFER_CORS_ORIGINS", raising=False)


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/v1/ping")
    async def _ping() -> dict[str, str]:
        return {"pong": "yes"}

    host_guard.install(app)
    return app


@pytest.fixture
def daemon(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The real application (every route, the real middleware stack), no lifespan."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_WEBUI_DIR", str(tmp_path / "no-ui"))
    set_active_token("tok")
    yield TestClient(create_app(), base_url=_BASE)
    set_active_token(None)


# -- Host ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "authority",
    ["127.0.0.1:8000", "localhost:8000", "LOCALHOST:8000", "[::1]:8000"],
)
def test_loopback_authorities_on_the_daemon_port_are_accepted(authority: str) -> None:
    client = TestClient(_app(), base_url=_BASE)
    r = client.get("/api/v1/ping", headers={"Host": authority})
    assert r.status_code == 200, authority


@pytest.mark.acceptance(
    spec="daemon",
    scenario="a rebound page is refused before it can read the token",
)
@pytest.mark.parametrize(
    "authority",
    [
        "evil.example:8000",
        "evil.example",
        "coffer.evil.example:8000",
        "192.168.1.4:8000",
        "localhost.evil.example:8000",
        "127.0.0.1.evil.example:8000",
        # Loopback, but not the port this request arrived on.
        "127.0.0.1:9999",
        "localhost:3000",
        # No port means :80, which is not the daemon's.
        "127.0.0.1",
        "localhost",
        # A bare IPv6 literal is not a well-formed Host.
        "::1",
    ],
)
def test_any_other_authority_is_refused(authority: str) -> None:
    """Under rebinding the browser still sends the attacker's own hostname."""
    client = TestClient(_app(), base_url=_BASE)
    r = client.get("/api/v1/ping", headers={"Host": authority})
    assert r.status_code == 403, authority
    assert r.json()["error"]["code"] == "HOST_NOT_ALLOWED"


@pytest.mark.acceptance(
    spec="daemon",
    scenario="a rebound page is refused before it can read the token",
)
def test_a_rebound_request_for_the_served_page_is_refused(daemon: TestClient) -> None:
    r = daemon.get("/", headers={"Host": "evil.example:8000"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "HOST_NOT_ALLOWED"
    assert "tok" not in r.text


def test_a_request_with_no_host_header_is_refused() -> None:
    """No browser omits Host, so the empty case has nothing legitimate to lose."""
    assert host_guard.is_allowed_host(None, _PORT) is False
    assert host_guard.is_allowed_host("", _PORT) is False


def test_the_escape_hatch_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    """``COFFER_ALLOWED_HOSTS`` names extra hostnames; ``*`` disables the check."""
    assert host_guard.is_allowed_host("testserver:8000", _PORT) is False
    monkeypatch.setenv("COFFER_ALLOWED_HOSTS", "testserver")
    assert host_guard.is_allowed_host("testserver:8000", _PORT) is True
    assert host_guard.is_allowed_host("testserver:9999", _PORT) is False
    assert host_guard.is_allowed_host("evil.example:8000", _PORT) is False
    monkeypatch.setenv("COFFER_ALLOWED_HOSTS", "*")
    assert host_guard.is_allowed_host("evil.example", _PORT) is True


# -- Origin -------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="daemon",
    scenario="a request from a page on another site is refused on every surface",
)
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/skills"),
        ("POST", "/api/v1/daemon/rotate-token"),
        ("POST", "/mcp"),
        ("GET", "/mcp"),
        ("GET", "/api/v1/events"),
        ("GET", "/api/v1/daemon/status"),
        ("GET", "/"),
        ("OPTIONS", "/api/v1/skills"),
    ],
)
@pytest.mark.parametrize(
    "origin",
    [_EVIL, "http://localhost:5173", "http://127.0.0.1:9999", "null"],
)
def test_a_foreign_origin_is_refused_on_every_surface(
    daemon: TestClient, method: str, path: str, origin: str
) -> None:
    """Even carrying the right token and the right Host: a foreign page's
    request never reaches a route. The Vite origin is foreign without the
    opt-in, and so is loopback on another port."""
    headers = {"Origin": origin, "X-Coffer-Token": "tok"}
    if method == "OPTIONS":
        headers["Access-Control-Request-Method"] = "GET"
    r = daemon.request(method, path, headers=headers)
    assert r.status_code == 403, (method, path, origin, r.text)
    assert r.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
    assert "access-control-allow-origin" not in r.headers


@pytest.mark.acceptance(
    spec="daemon",
    scenario="Coffer's own pages and clients that send no Origin are let through",
)
@pytest.mark.parametrize(
    "origin",
    [
        None,  # the CLI, the shim, an agent's MCP client, curl
        f"http://127.0.0.1:{_PORT}",
        f"http://localhost:{_PORT}",
        f"http://[::1]:{_PORT}",
        "tauri://localhost",
        "http://tauri.localhost",
    ],
)
def test_own_origins_and_no_origin_reach_the_token_check(
    daemon: TestClient, origin: str | None
) -> None:
    headers = {} if origin is None else {"Origin": origin}
    assert daemon.get("/api/v1/daemon/status", headers=headers).status_code == 200
    # A management route answers its own auth check, so the guard let it by.
    assert daemon.get("/api/v1/skills", headers=headers).status_code == 401
    assert daemon.post("/mcp", headers=headers, json={}).status_code == 401
    assert daemon.get("/api/v1/events", headers=headers).status_code == 401


def test_the_desktop_shell_preflight_is_still_answered(daemon: TestClient) -> None:
    r = daemon.options(
        "/api/v1/skills",
        headers={
            "Origin": "tauri://localhost",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Coffer-Token",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "tauri://localhost"


@pytest.mark.acceptance(
    spec="daemon",
    scenario="a development origin is let through only when opted in",
)
def test_a_dev_origin_needs_the_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_WEBUI_DIR", str(tmp_path / "no-ui"))
    vite = {"Origin": "http://localhost:5173"}

    plain = TestClient(create_app(), base_url=_BASE)
    assert plain.get("/api/v1/daemon/status", headers=vite).status_code == 403

    monkeypatch.setenv("COFFER_DEV_CORS", "1")
    dev = TestClient(create_app(), base_url=_BASE)
    assert dev.get("/api/v1/daemon/status", headers=vite).status_code == 200
    assert dev.get("/api/v1/daemon/status", headers={"Origin": _EVIL}).status_code == 403

    monkeypatch.delenv("COFFER_DEV_CORS")
    monkeypatch.setenv("COFFER_CORS_ORIGINS", "http://localhost:5174")
    listed = TestClient(create_app(), base_url=_BASE)
    spare = {"Origin": "http://localhost:5174"}
    assert listed.get("/api/v1/daemon/status", headers=spare).status_code == 200
    assert listed.get("/api/v1/daemon/status", headers=vite).status_code == 403
    # The daemon's own origin needs no listing, whatever the list says.
    own = {"Origin": _BASE}
    assert listed.get("/api/v1/daemon/status", headers=own).status_code == 200


def test_each_refused_value_is_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    host_guard._logged.clear()
    client = TestClient(_app(), base_url=_BASE)
    with caplog.at_level("WARNING", logger=host_guard.__name__):
        for _ in range(3):
            client.get("/api/v1/ping", headers={"Origin": "https://once.example"})
        client.get("/api/v1/ping", headers={"Origin": "https://twice.example"})
    refused = [r for r in caplog.records if r.getMessage() == "http.request_refused"]
    assert [getattr(r, "value", None) for r in refused] == [
        "https://once.example",
        "https://twice.example",
    ]


def test_a_websocket_handshake_from_a_foreign_origin_is_closed() -> None:
    app = FastAPI()

    @app.websocket("/ws")
    async def _ws(ws: WebSocket) -> None:  # pragma: no cover - never reached
        await ws.accept()

    host_guard.install(app)
    client = TestClient(app, base_url=_BASE)
    with (
        pytest.raises(WebSocketDisconnect) as refused,
        client.websocket_connect("/ws", headers={"Origin": _EVIL}),
    ):
        pass  # pragma: no cover
    assert refused.value.code == 1008
