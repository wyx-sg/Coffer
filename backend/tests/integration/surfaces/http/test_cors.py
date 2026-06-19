"""CORS preflight behaviour for browser-origin write requests.

The Vite dev UI talks to the daemon cross-origin (``localhost:5173`` →
``127.0.0.1:8000``). Any non-simple request (JSON body, custom header) triggers
a CORS preflight; the browser blocks the real request unless the preflight
allows its method. ``PUT`` was missing from the allowlist, so every ``PUT``
endpoint (credential settings, agent config files, sync/embedding config, …)
failed in the browser with "Failed to fetch" even though the server itself was
healthy.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _app_with_cors(monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    monkeypatch.delenv("COFFER_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("COFFER_DEV_CORS", "1")
    from coffer.surfaces.http import cors

    app = FastAPI()

    @app.put("/echo")
    async def _echo() -> dict[str, str]:  # pragma: no cover - body never hit in preflight
        return {"ok": "yes"}

    cors.install(app)
    return app


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_cors_preflight_allows_write_methods(monkeypatch: pytest.MonkeyPatch, method: str) -> None:
    """The browser preflight (OPTIONS) must succeed for every method the API
    actually exposes — Starlette answers 400 "Disallowed CORS method" when the
    requested method is absent from ``allow_methods``."""
    client = TestClient(_app_with_cors(monkeypatch))
    resp = client.options(
        "/echo",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "x-coffer-token,content-type",
        },
    )
    assert resp.status_code == 200, resp.text
    assert method in resp.headers.get("access-control-allow-methods", "")
