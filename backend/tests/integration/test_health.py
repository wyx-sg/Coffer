import os

from fastapi.testclient import TestClient

from coffer.surfaces.http.app import create_app


def test_daemon_status_endpoint_returns_ready(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    os.environ["HOME"] = str(tmp_path)
    os.environ["COFFER_DB_URL"] = f"sqlite+aiosqlite:///{tmp_path / 'c.db'}"

    app = create_app()
    # TestClient used as context manager drives the ASGI lifespan
    with TestClient(app) as client:
        response = client.get("/api/v1/daemon/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert "version" in payload
    assert "started_at" in payload
    assert "port" in payload
