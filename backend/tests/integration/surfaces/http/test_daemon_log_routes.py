"""``GET /api/v1/daemon/logs`` — the daemon log, read by a human on one page.

``coffer__diagnose`` already answers this for an agent. The Activity page needs
the same tail over HTTP, with the same two decisions preserved: newest-first,
and an unparseable line kept rather than dropped.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from coffer.surfaces.http import daemon_routes
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.daemon_routes import router as daemon_router


def _json_line(level: str, event: str, *, at: datetime | None = None) -> str:
    return json.dumps(
        {
            "timestamp": (at or datetime.now(tz=UTC)).isoformat(),
            "level": level,
            "event": event,
        }
    )


def _write_log(monkeypatch, tmp_path: Path, lines: list[str] | None) -> None:
    """Point the route's ``log_dir`` at a tmp dir, optionally with a log in it."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(exist_ok=True)
    if lines is not None:
        (log_dir / "daemon.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(daemon_routes, "log_dir", lambda: log_dir)


def _client(*, token: str | None = "test-token") -> AsyncClient:
    set_active_token("test-token")
    app = FastAPI()
    err_handlers.register(app)
    app.include_router(daemon_router)
    headers = {"X-Coffer-Token": token} if token else {}
    return AsyncClient(transport=ASGITransport(app), base_url="http://t", headers=headers)


@pytest.mark.asyncio
async def test_logs_require_a_token(monkeypatch, tmp_path) -> None:
    """The router itself is unauthenticated so /status can be a readiness probe.
    Log contents are not probe material and must not ride that exemption."""
    _write_log(monkeypatch, tmp_path, [_json_line("info", "coffer.started")])
    async with _client(token=None) as c:
        assert (await c.get("/api/v1/daemon/logs")).status_code == 401
        # …while the probe next door stays open.
        assert (await c.get("/api/v1/daemon/status")).status_code == 200


@pytest.mark.asyncio
async def test_newest_first(monkeypatch, tmp_path) -> None:
    now = datetime.now(tz=UTC)
    _write_log(
        monkeypatch,
        tmp_path,
        [
            _json_line("info", "older", at=now - timedelta(minutes=2)),
            _json_line("info", "newer", at=now - timedelta(minutes=1)),
        ],
    )
    async with _client() as c:
        r = await c.get("/api/v1/daemon/logs")
    assert r.status_code == 200
    assert [rec["event"] for rec in r.json()["records"]] == ["newer", "older"]


@pytest.mark.asyncio
async def test_errors_only_keeps_errors_and_unparseable_lines(monkeypatch, tmp_path) -> None:
    _write_log(
        monkeypatch,
        tmp_path,
        [
            _json_line("info", "coffer.resource_created"),
            _json_line("error", "mcp.upstream.spawn_failed"),
            "Traceback (most recent call last):",
        ],
    )
    async with _client() as c:
        r = await c.get("/api/v1/daemon/logs", params={"errors_only": True})
    records = r.json()["records"]
    assert [rec["event"] or rec["record"]["raw"] for rec in records] == [
        "Traceback (most recent call last):",
        "mcp.upstream.spawn_failed",
    ]


@pytest.mark.asyncio
async def test_an_unparseable_line_survives_as_raw(monkeypatch, tmp_path) -> None:
    """A traceback is not JSON and is usually the most interesting line."""
    _write_log(monkeypatch, tmp_path, ["  ValueError: x"])
    async with _client() as c:
        r = await c.get("/api/v1/daemon/logs")
    [record] = r.json()["records"]
    assert record["record"] == {"raw": "  ValueError: x"}
    assert record["timestamp"] is None
    assert record["level"] is None
    assert record["event"] is None


@pytest.mark.asyncio
async def test_a_missing_log_file_is_an_empty_list_not_a_500(monkeypatch, tmp_path) -> None:
    """A fresh install has no daemon.log yet; the page must still render."""
    _write_log(monkeypatch, tmp_path, None)
    async with _client() as c:
        r = await c.get("/api/v1/daemon/logs")
    assert r.status_code == 200
    assert r.json() == {"records": []}


@pytest.mark.asyncio
async def test_since_stops_at_the_first_older_line(monkeypatch, tmp_path) -> None:
    now = datetime.now(tz=UTC)
    _write_log(
        monkeypatch,
        tmp_path,
        [
            _json_line("info", "ancient", at=now - timedelta(days=3)),
            _json_line("info", "recent", at=now - timedelta(minutes=5)),
        ],
    )
    since = (now - timedelta(minutes=30)).isoformat()
    async with _client() as c:
        r = await c.get("/api/v1/daemon/logs", params={"since": since})
    assert [rec["event"] for rec in r.json()["records"]] == ["recent"]


@pytest.mark.asyncio
async def test_since_in_another_timezone_names_the_same_instant(monkeypatch, tmp_path) -> None:
    """The window is an instant, not a spelling.

    The log writes UTC, and the filter compares ISO strings; a caller passing
    the same moment as ``+08:00`` must get the same window back, not an empty
    one because ``+`` sorts below ``Z``.
    """
    now = datetime.now(tz=UTC)
    _write_log(
        monkeypatch,
        tmp_path,
        [
            _json_line("info", "ancient", at=now - timedelta(days=3)),
            _json_line("info", "recent", at=now - timedelta(minutes=5)),
        ],
    )
    since = (now - timedelta(minutes=30)).astimezone(timezone(timedelta(hours=8))).isoformat()
    async with _client() as c:
        r = await c.get("/api/v1/daemon/logs", params={"since": since})
    assert [rec["event"] for rec in r.json()["records"]] == ["recent"]


@pytest.mark.asyncio
async def test_limit_is_bounded(monkeypatch, tmp_path) -> None:
    _write_log(monkeypatch, tmp_path, [_json_line("info", f"e{i}") for i in range(10)])
    async with _client() as c:
        assert len((await c.get("/api/v1/daemon/logs", params={"limit": 3})).json()["records"]) == 3
        assert (await c.get("/api/v1/daemon/logs", params={"limit": 9999})).status_code == 422
