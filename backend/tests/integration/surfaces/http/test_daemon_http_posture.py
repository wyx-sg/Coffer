"""The daemon's HTTP posture over the real application: every management route
is token-gated, and the web UI is served same-origin with cross-origin access
off unless a developer opts in.

The app is built with ``create_app()`` under a throwaway ``HOME`` and database;
no port is bound and ``~/.coffer`` is never read.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_TOKEN = "the-active-token"


@pytest.fixture
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.delenv("COFFER_DEV_CORS", raising=False)
    monkeypatch.delenv("COFFER_CORS_ORIGINS", raising=False)
    set_active_token(_TOKEN)
    yield
    set_active_token(None)


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", path)


@pytest.mark.acceptance(spec="daemon", scenario="a management call without the token is refused")
def test_every_management_route_refuses_a_missing_or_wrong_token(
    _isolated: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COFFER_WEBUI_DIR", str(tmp_path / "no-ui"))
    app = create_app()
    routes = [
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/")
        for method in sorted(route.methods - {"HEAD", "OPTIONS"})
    ]
    assert len(routes) >= 50, "the management API must be enumerated, not an empty list"

    client = TestClient(app, base_url="http://127.0.0.1")
    unguarded: list[str] = []
    for method, path in routes:
        if path == "/api/v1/daemon/status":
            continue
        url = _concrete(path)
        for headers in ({}, {"X-Coffer-Token": "not-the-token"}):
            r = client.request(method, url, headers=headers)
            if r.status_code != 401:
                unguarded.append(f"{method} {path} {headers or 'no token'} -> {r.status_code}")
    assert unguarded == [], "\n".join(unguarded)

    status = client.get("/api/v1/daemon/status")
    assert status.status_code == 200


def _built_ui(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Coffer UI</title>")
    (dist / "assets" / "app.js").write_text("console.log('coffer')")
    return dist


def _preflight(client: TestClient, origin: str) -> str | None:
    r = client.options(
        "/api/v1/skills",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Coffer-Token",
        },
    )
    return r.headers.get("access-control-allow-origin")


@pytest.mark.acceptance(
    spec="daemon",
    scenario="the built UI is served same-origin and a missing build leaves the API up",
)
def test_the_ui_is_same_origin_and_cross_origin_is_opt_in(
    _isolated: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COFFER_WEBUI_DIR", str(_built_ui(tmp_path)))
    client = TestClient(create_app(), base_url="http://127.0.0.1:8000")

    page = client.get("/")
    assert page.status_code == 200 and "Coffer UI" in page.text
    asset = client.get("/assets/app.js")
    assert asset.status_code == 200 and "coffer" in asset.text

    assert _preflight(client, "https://evil.example") is None
    assert _preflight(client, "http://localhost:5173") is None
    assert _preflight(client, "http://127.0.0.1:5173") is None

    monkeypatch.setenv("COFFER_DEV_CORS", "1")
    dev = TestClient(create_app(), base_url="http://127.0.0.1:8000")
    assert _preflight(dev, "http://localhost:5173") == "http://localhost:5173"
    assert _preflight(dev, "https://evil.example") is None

    monkeypatch.delenv("COFFER_DEV_CORS")
    monkeypatch.setenv("COFFER_WEBUI_DIR", str(tmp_path / "never-built"))
    bare = TestClient(create_app(), base_url="http://127.0.0.1:8000")
    assert bare.get("/api/v1/daemon/status").status_code == 200
    # A management route is still mounted: it answers its own auth check, not a 404.
    assert bare.get("/api/v1/skills").status_code == 401
    assert bare.get("/").status_code == 404
