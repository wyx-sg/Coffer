"""The daemon serving the built web UI (spec mcp-gateway FR-024/FR-025).

Two load-bearing properties. Mounting a SPA at ``/`` must not swallow the API.
And every route that ends at ``index.html`` must carry the daemon's live token,
uncacheable — that document is how the browser gets authenticated, and a cached
copy would hand a restarted daemon's browser the previous daemon's dead token.
Everything else here is about degrading quietly when no UI was built.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from coffer.surfaces.http import webui
from coffer.surfaces.http.auth import set_active_token


@pytest.fixture(autouse=True)
def _live_token() -> Iterator[None]:
    """A daemon with a published token, as every served page assumes."""
    set_active_token("live-daemon-token")
    yield
    set_active_token(None)


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


# ---------------------------------------------------------------------------
# The token the served document carries (spec mcp-gateway FR-025)
# ---------------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="a page served by the daemon is authenticated by the daemon",
)
@pytest.mark.parametrize("route", ["/", "/index.html", "/agents", "/mcp-servers/foo"])
def test_every_route_that_serves_index_carries_the_live_token(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, route: str
) -> None:
    """A bookmark, a typed URL and a reload must all land authenticated.

    The user's failing page was `/agents` — a client-side route served through
    the SPA fallback — so covering only `/` would fix nothing.
    """
    client = TestClient(_app(monkeypatch, _built_ui(tmp_path)))
    r = client.get(route)
    assert r.status_code == 200
    assert 'window.__COFFER_TOKEN__="live-daemon-token"' in r.text


def test_the_served_index_is_never_cached(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """It holds a per-daemon secret, so a cached copy is a stale credential.

    No validators either: an ETag or Last-Modified would let the browser
    revalidate its way back to the previous daemon's token, which is the exact
    failure the injection exists to end.
    """
    client = TestClient(_app(monkeypatch, _built_ui(tmp_path)))
    r = client.get("/agents")
    assert r.headers["cache-control"] == "no-store"
    assert "etag" not in r.headers
    assert "last-modified" not in r.headers


def test_hashed_assets_keep_their_normal_caching(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Only index.html is special; /assets/* is content-hashed and cacheable."""
    client = TestClient(_app(monkeypatch, _built_ui(tmp_path)))
    r = client.get("/assets/app.js")
    assert r.status_code == 200
    assert r.headers.get("cache-control") != "no-store"
    assert "etag" in r.headers


def test_the_injected_token_follows_a_rotation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Read per request from the same variable `require_token` compares against.

    `POST /daemon/rotate-token` republishes that one variable, so the value the
    page is handed cannot drift from the value the API accepts.
    """
    client = TestClient(_app(monkeypatch, _built_ui(tmp_path)))
    set_active_token("rotated-token")
    assert 'window.__COFFER_TOKEN__="rotated-token"' in client.get("/").text


def test_no_token_script_before_the_daemon_publishes_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """During startup there is no token; serve the page rather than a blank."""
    client = TestClient(_app(monkeypatch, _built_ui(tmp_path)))
    set_active_token(None)
    r = client.get("/")
    assert r.status_code == 200
    assert "__COFFER_TOKEN__" not in r.text


def test_the_token_script_goes_first_inside_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """It must run before the bundle does, or the first query goes out bare."""
    dist = _built_ui(tmp_path)
    (dist / "index.html").write_text(
        "<!doctype html><html><head><title>Coffer</title></head>"
        '<body><script src="/assets/app.js"></script></body></html>'
    )
    client = TestClient(_app(monkeypatch, dist))
    body = client.get("/").text
    assert body.index("__COFFER_TOKEN__") < body.index("/assets/app.js")
