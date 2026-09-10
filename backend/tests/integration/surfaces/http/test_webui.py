"""The daemon serving the built web UI (spec mcp-gateway FR-024).

The load-bearing property is that mounting a SPA at ``/`` must not swallow the
API. Everything else here is about degrading quietly when no UI was built.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coffer.surfaces.http import webui


def _built_ui(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Coffer</title>")
    (dist / "assets" / "app.js").write_text("console.log('hi')")
    return dist


def _app(monkeypatch: pytest.MonkeyPatch, dist: Path | None) -> FastAPI:
    if dist is None:
        monkeypatch.setenv("COFFER_WEBUI_DIR", "/nonexistent-webui-dir")
    else:
        monkeypatch.setenv("COFFER_WEBUI_DIR", str(dist))

    app = FastAPI()

    @app.get("/api/v1/ping")
    async def _ping() -> dict[str, str]:
        return {"pong": "yes"}

    webui.install(app)
    return app


def test_serves_index_at_the_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = TestClient(_app(monkeypatch, _built_ui(tmp_path)))
    r = client.get("/")
    assert r.status_code == 200
    assert "Coffer" in r.text


def test_serves_hashed_assets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    client = TestClient(_app(monkeypatch, _built_ui(tmp_path)))
    assert client.get("/assets/app.js").status_code == 200


def test_client_side_routes_fall_back_to_index(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A deep link the browser requests from the daemon has no file on disk;
    serving index.html lets the client-side router take over."""
    client = TestClient(_app(monkeypatch, _built_ui(tmp_path)))
    r = client.get("/mcp-servers")
    assert r.status_code == 200
    assert "Coffer" in r.text


def test_api_routes_are_not_shadowed_by_the_mount(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The whole point of mounting last: the API still answers."""
    client = TestClient(_app(monkeypatch, _built_ui(tmp_path)))
    r = client.get("/api/v1/ping")
    assert r.status_code == 200
    assert r.json() == {"pong": "yes"}


def test_api_404s_stay_404(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """An unknown API path must NOT come back as the SPA's index.html — that
    would turn every client bug into a confusing 200 full of HTML."""
    client = TestClient(_app(monkeypatch, _built_ui(tmp_path)))
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert "<!doctype html>" not in r.text.lower()


def test_no_mount_when_nothing_was_built(monkeypatch: pytest.MonkeyPatch) -> None:
    """A backend-only install serves the API and nothing else, rather than
    failing to start on a missing directory."""
    client = TestClient(_app(monkeypatch, None))
    assert client.get("/api/v1/ping").status_code == 200
    assert client.get("/").status_code == 404


def test_resolve_honours_the_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dist = _built_ui(tmp_path)
    monkeypatch.setenv("COFFER_WEBUI_DIR", str(dist))
    assert webui.resolve_webui_dir() == dist


def test_resolve_rejects_a_directory_without_index(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("COFFER_WEBUI_DIR", str(empty))
    assert webui.resolve_webui_dir() is None


@pytest.mark.parametrize(
    "route", ["/mcp-servers", "/mcp-servers/foo", "/api-keys", "/health-check"]
)
def test_ui_routes_that_merely_start_like_a_daemon_surface_still_resolve(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, route: str
) -> None:
    """Reserved roots match whole path segments, not bare prefixes.

    `/mcp-servers` is a real UI route and `/mcp` is a real API surface. A
    `startswith("mcp")` guard would 404 the page the user actually asked for.
    """
    client = TestClient(_app(monkeypatch, _built_ui(tmp_path)))
    r = client.get(route)
    assert r.status_code == 200
    assert "Coffer" in r.text


# `/openapi.json` is deliberately absent: the real app serves its schema at
# /api/v1/openapi.json, and a bare FastAPI() answers /openapi.json itself, so
# the request never reaches the mount here.
@pytest.mark.parametrize("route", ["/api/v1/nope", "/mcp", "/health"])
def test_daemon_surfaces_404_rather_than_returning_the_spa(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, route: str
) -> None:
    client = TestClient(_app(monkeypatch, _built_ui(tmp_path)))
    r = client.get(route)
    assert r.status_code == 404
    assert "<!doctype html>" not in r.text.lower()
