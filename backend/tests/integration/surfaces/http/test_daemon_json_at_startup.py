"""Lifespan reads ``daemon.json``: absent is skipped, unreadable fails startup.

``entry.py`` writes daemon.json before uvicorn starts, so a daemon that finds
the file present but unreadable at lifespan has a real fault. Swallowing it
used to leave the API token unset — every authenticated route answered 503
while ``/daemon/status`` reported ``ready``.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from coffer.surfaces.http.app import create_app


def _point_at(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    coffer_dir = tmp_path / ".coffer"
    coffer_dir.mkdir()
    return coffer_dir / "daemon.json"


@pytest.mark.asyncio
async def test_unreadable_daemon_json_fails_startup(tmp_path: Path, monkeypatch, caplog) -> None:
    path = _point_at(tmp_path, monkeypatch)
    path.write_text("{not json")
    app = create_app()
    with (
        caplog.at_level(logging.ERROR),
        pytest.raises(RuntimeError, match=r"daemon\.json .* unreadable"),
    ):
        async with app.router.lifespan_context(app):
            pass
    # Asserted on the record, not on a rendered line. This used to grep the
    # daemon's stderr for the word "ERROR", which the daemon's own formatter no
    # longer writes (a line states `"level": "error"`) — and which a message
    # merely mentioning an error would have satisfied anyway. The record is
    # what the requirement is about: the fault must be logged at error level,
    # not only raised.
    faults = [r for r in caplog.records if "daemon.json" in r.getMessage()]
    assert faults, "the fault must be logged, not only raised"
    assert [r.levelname for r in faults] == ["ERROR"]
    assert "unreadable" in faults[0].getMessage()


@pytest.mark.asyncio
async def test_daemon_json_missing_a_field_fails_startup(tmp_path: Path, monkeypatch) -> None:
    path = _point_at(tmp_path, monkeypatch)
    path.write_text(json.dumps({"version": 1, "pid": 1, "port": 8000}))  # no token
    app = create_app()
    with pytest.raises(RuntimeError, match="unreadable"):
        async with app.router.lifespan_context(app):
            pass


@pytest.mark.asyncio
async def test_readable_daemon_json_publishes_its_token(tmp_path: Path, monkeypatch) -> None:
    path = _point_at(tmp_path, monkeypatch)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "pid": 1,
                "port": 8123,
                "token": "tok-from-file",
                "started_at": datetime.now(tz=UTC).isoformat(),
                "binary_path": "/x",
            }
        )
    )
    app = create_app()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app), base_url="http://t") as c,
    ):
        status = await c.get("/api/v1/daemon/status")
        denied = await c.get("/api/v1/resources")
        allowed = await c.get("/api/v1/resources", headers={"X-Coffer-Token": "tok-from-file"})
    assert status.json()["port"] == 8123
    assert denied.status_code in (401, 403)
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_absent_daemon_json_is_skipped(tmp_path: Path, monkeypatch) -> None:
    """The in-process path (tests, `uvicorn coffer.main:app`) has no file to read."""
    _point_at(tmp_path, monkeypatch)
    app = create_app()
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app), base_url="http://t") as c,
    ):
        r = await c.get("/api/v1/daemon/status")
    assert r.json()["status"] == "ready"
