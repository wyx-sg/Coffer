"""An in-process daemon serving only /api/v1/sync (and the master key routes
under /api/v1/secrets/key) over a real sync service."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.secret_key_routes import router as key_router
from coffer.surfaces.http.secret_key_routes import set_master_key_service
from coffer.surfaces.http.sync_dependencies import set_sync_service
from coffer.surfaces.http.sync_routes import router

from .harness import Box, joined

TOKEN = "test-token"


def client_for(box: Box) -> TestClient:
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(router)
    app.include_router(key_router, prefix="/api/v1/secrets")
    set_sync_service(box.service)
    set_master_key_service(box.keys)
    return TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": TOKEN},
        raise_server_exceptions=False,
    )


@pytest.fixture
def pair(tmp_path: Path) -> Iterator[tuple[Box, Box]]:
    set_active_token(TOKEN)
    yield tuple(joined(tmp_path, "Mac", "Mini"))  # type: ignore[misc]
    set_active_token(None)
    set_sync_service(None)
    set_master_key_service(None)
