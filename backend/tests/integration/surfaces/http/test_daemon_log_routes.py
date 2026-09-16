"""``GET /api/v1/daemon/logs`` — the daemon log, read by a human on one page.

``coffer__diagnose`` already answers this for an agent. The Activity page needs
the same tail over HTTP, with the same decisions preserved: newest-first, a
line no writer's format fits kept rather than dropped, and — because the file
interleaves several writers at once — every row carrying the time, level and
logger its own line stated.
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
            "Will assume non-transactional DDL.",
        ],
    )
    async with _client() as c:
        r = await c.get("/api/v1/daemon/logs", params={"errors_only": True})
    records = r.json()["records"]
    assert [rec["event"] or rec["record"]["raw"] for rec in records] == [
        "Will assume non-transactional DDL.",
        "mcp.upstream.spawn_failed",
    ]


@pytest.mark.asyncio
async def test_a_level_floor_keeps_everything_at_or_above_it(monkeypatch, tmp_path) -> None:
    """A floor, not an exact match.

    "Warnings" means warnings AND the errors among them: a reader narrowing to
    warnings is asking to stop reading info chatter, not to stop being told
    about the failures that chatter was leading up to.
    """
    _write_log(
        monkeypatch,
        tmp_path,
        [
            _json_line("debug", "cache.miss"),
            _json_line("info", "coffer.resource_created"),
            _json_line("warning", "codex.stderr_relayed"),
            _json_line("error", "mcp.upstream.spawn_failed"),
        ],
    )
    async with _client() as c:
        r = await c.get("/api/v1/daemon/logs", params={"level": "warning"})

    assert [rec["event"] for rec in r.json()["records"]] == [
        "mcp.upstream.spawn_failed",
        "codex.stderr_relayed",
    ]


@pytest.mark.asyncio
async def test_a_level_floor_reads_an_upstreams_own_spelling(monkeypatch, tmp_path) -> None:
    # cloudflared writes zerolog's three-letter levels into the same file; the
    # floor has to mean the same thing for them as for structlog's own words.
    _write_log(
        monkeypatch,
        tmp_path,
        [
            "2026-09-14T06:29:20Z INF Registered tunnel connection",
            "2026-09-14T06:29:21Z WRN Retrying connection",
        ],
    )
    async with _client() as c:
        r = await c.get("/api/v1/daemon/logs", params={"level": "warning"})

    assert [rec["event"] for rec in r.json()["records"]] == ["Retrying connection"]


@pytest.mark.asyncio
async def test_no_level_floor_filters_nothing(monkeypatch, tmp_path) -> None:
    _write_log(monkeypatch, tmp_path, [_json_line("debug", "cache.miss")])
    async with _client() as c:
        r = await c.get("/api/v1/daemon/logs")

    assert [rec["event"] for rec in r.json()["records"]] == ["cache.miss"]


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="web-ui", scenario="the daemon tab reads every writer in the log")
async def test_errors_only_reads_every_writers_own_level(monkeypatch, tmp_path) -> None:
    """The log is not all structlog. An `INF` line from the cloudflared child
    is an info line — before, every non-JSON line counted as an error and the
    filter kept the entire file."""
    _write_log(
        monkeypatch,
        tmp_path,
        [
            "2026-09-14T06:29:13Z INF Starting tunnel tunnelID=8b625f11",
            "2026-09-14T05:05:23Z ERR failed to serve incoming request",
            "INFO  [alembic.runtime.migration] Context impl SQLiteImpl.",
            "ERROR:    ASGI callable returned without completing response.",
        ],
    )
    async with _client() as c:
        r = await c.get("/api/v1/daemon/logs", params={"errors_only": True})
    assert [rec["event"] for rec in r.json()["records"]] == [
        "ASGI callable returned without completing response.",
        "failed to serve incoming request",
    ]


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="web-ui", scenario="the daemon tab reads every writer in the log")
@pytest.mark.acceptance(spec="daemon", scenario="the daemon log tail reads every writer's format")
async def test_every_format_in_the_file_fills_the_three_columns(monkeypatch, tmp_path) -> None:
    """The page shows time / level / logger / message. ``daemon.log`` carries
    several writers' formats at once, and a row must carry what its own line
    stated rather than dumping the whole line into the message column."""
    _write_log(
        monkeypatch,
        tmp_path,
        [
            "2026-09-14T06:29:20Z INF precheck complete hard_fail=false",
            "WARNI [coffer.application.knowledge.skill_seed] knowledge.skill_seed.missing_asset",
            "ERROR:    ASGI callable returned without completing response.",
            "WARNING - mcp_atlassian.utils.toolsets - TOOLSETS is not set",
        ],
    )
    async with _client() as c:
        r = await c.get("/api/v1/daemon/logs")
    records = r.json()["records"]
    assert [rec["level"] for rec in records] == ["warning", "error", "warning", "info"]
    assert [rec["record"].get("logger") for rec in records] == [
        "mcp_atlassian.utils.toolsets",
        None,
        "coffer.application.knowledge.skill_seed",
        None,
    ]
    # Only the zerolog line stated a time; nothing invents one for the others.
    assert [rec["timestamp"] for rec in records] == [
        None,
        None,
        None,
        "2026-09-14T06:29:20Z",
    ]


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="web-ui", scenario="the daemon tab reads every writer in the log")
async def test_a_colour_escaped_line_arrives_without_escapes(monkeypatch, tmp_path) -> None:
    """The Codex app-server colours its stderr even into a pipe, and the daemon
    relays it verbatim. A viewer rendering `ESC[31m` as text is broken."""
    _write_log(
        monkeypatch,
        tmp_path,
        [
            "WARNI [coffer.infrastructure.chat.codex_app_server] codex app-server stderr: "
            "\x1b[31mERROR\x1b[0m \x1b[2mcodex_models_manager::cache\x1b[0m: failed to load"
        ],
    )
    async with _client() as c:
        r = await c.get("/api/v1/daemon/logs")
    [record] = r.json()["records"]
    assert record["level"] == "warning"
    assert record["record"]["logger"] == "coffer.infrastructure.chat.codex_app_server"
    assert "\x1b" not in record["event"] and "[31m" not in record["event"]
    assert record["event"].endswith("ERROR codex_models_manager::cache: failed to load")


@pytest.mark.asyncio
@pytest.mark.acceptance(spec="web-ui", scenario="the daemon tab reads every writer in the log")
async def test_a_traceback_rides_with_the_record_that_raised(monkeypatch, tmp_path) -> None:
    """Otherwise a single failure fills the table with rows that have no time,
    no level and no logger, and pushes the record explaining them off the page."""
    _write_log(
        monkeypatch,
        tmp_path,
        [
            "ERROR [coffer.memory.consolidate] consolidate.store.failed store=project-61Z8Q9",
            "Traceback (most recent call last):",
            '  File "coffer/application/memory/consolidate.py", line 159, in run',
            "openai.RateLimitError: Error code: 429 - rate limit reached",
        ],
    )
    async with _client() as c:
        r = await c.get("/api/v1/daemon/logs")
    [record] = r.json()["records"]
    assert record["level"] == "error"
    assert record["event"] == "consolidate.store.failed store=project-61Z8Q9"
    assert record["record"]["continuation"][-1] == (
        "openai.RateLimitError: Error code: 429 - rate limit reached"
    )


@pytest.mark.asyncio
async def test_an_unparseable_line_survives_as_raw(monkeypatch, tmp_path) -> None:
    """A line no writer's format fits is kept whole rather than dropped."""
    _write_log(monkeypatch, tmp_path, ["Will assume non-transactional DDL."])
    async with _client() as c:
        r = await c.get("/api/v1/daemon/logs")
    [record] = r.json()["records"]
    assert record["record"] == {"raw": "Will assume non-transactional DDL."}
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
