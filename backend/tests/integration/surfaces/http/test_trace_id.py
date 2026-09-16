"""A response's trace id must be an id, and must be the one the log records carry.

The daemon shipped the whole trace-id facility — contextvar, structlog
processor, ``X-Coffer-Trace`` on every error envelope — with nothing that ever
set the contextvar, so every header and every ``trace_id`` log field read the
``"-"`` sentinel. These tests pin the writer that fixes that, because an inert
correlation handle fails silently: the header is present, well-formed and
useless.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from coffer.infrastructure.logging.setup import _add_trace_id, get_trace_id
from coffer.surfaces.http import trace
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.trace import TRACE_HEADER, sanitize_trace_id


def _app(tmp_path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def test_successful_response_carries_a_real_trace_id(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59700)
    with TestClient(app) as c:
        r = c.get("/api/v1/daemon/status")
        assert r.status_code == 200
        trace = r.headers[TRACE_HEADER]
        # The bug this pins: the header was always the "-" sentinel.
        assert trace != "-"
        assert trace


def test_error_envelope_trace_id_is_not_the_sentinel(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59710)
    with TestClient(app) as c:
        set_active_token("real-token")
        r = c.get("/api/v1/resources")
        assert r.status_code == 401
        assert r.headers["X-Coffer-Trace"] != "-"


def test_two_requests_get_different_trace_ids(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59720)
    with TestClient(app) as c:
        first = c.get("/api/v1/daemon/status").headers[TRACE_HEADER]
        second = c.get("/api/v1/daemon/status").headers[TRACE_HEADER]
        assert first != second


def test_client_supplied_trace_id_is_echoed(tmp_path, monkeypatch):
    """The CLI and the MCP shim make several calls per user action; a shared id
    makes them one story in the log."""
    app = _app(tmp_path, monkeypatch, 59730)
    with TestClient(app) as c:
        r = c.get("/api/v1/daemon/status", headers={TRACE_HEADER: "cli-run-7"})
        assert r.headers[TRACE_HEADER] == "cli-run-7"


def test_host_guard_refusal_is_also_correlatable(tmp_path, monkeypatch):
    """The trace middleware is outermost, so even a request the host guard
    refuses before anything else looks at it comes back with an id."""
    monkeypatch.delenv("COFFER_ALLOWED_HOSTS", raising=False)
    app = _app(tmp_path, monkeypatch, 59740)
    with TestClient(app) as c:
        r = c.get("/api/v1/daemon/status", headers={"Host": "evil.com"})
        assert r.status_code == 421
        assert r.headers[TRACE_HEADER] != "-"


def test_the_route_reads_back_the_id_the_response_reports():
    """The point of the whole facility, and the part a middleware can get wrong.

    ``bind_trace_id`` writes a contextvar. If the middleware bound it in a
    different task from the one the route runs in — which is exactly what
    ``BaseHTTPMiddleware`` would have caused — the route (and every log record
    it produces, via the ``_add_trace_id`` structlog processor) would still read
    the ``"-"`` sentinel while the response header looked perfectly correct.
    """
    probe = FastAPI()

    @probe.get("/whoami")
    def whoami() -> dict[str, str]:
        return {"trace_id": get_trace_id()}

    trace.install(probe)
    with TestClient(probe) as c:
        r = c.get("/whoami")
    assert r.json()["trace_id"] == r.headers[TRACE_HEADER]
    assert r.json()["trace_id"] != "-"


def test_the_structlog_processor_stamps_the_bound_id():
    """``_add_trace_id`` is what puts the id on a log record; with the
    middleware bound it stamps the request's id instead of the sentinel."""
    probe = FastAPI()
    seen: dict[str, object] = {}

    @probe.get("/whoami")
    def whoami() -> dict[str, str]:
        seen.update(_add_trace_id(None, "info", {"event": "probe"}))
        return {"ok": "1"}

    trace.install(probe)
    with TestClient(probe) as c:
        r = c.get("/whoami")
    assert seen["trace_id"] == r.headers[TRACE_HEADER]
    assert seen["trace_id"] != "-"


def test_the_id_does_not_leak_past_the_request():
    """A background task that outlives the request must not log the request's
    id as if it were its own."""
    probe = FastAPI()
    trace.install(probe)
    with TestClient(probe) as c:
        c.get("/nope")  # 404 is fine; the middleware still ran
    assert get_trace_id() == "-"


@pytest.mark.parametrize(
    "raw",
    [
        "bad\nvalue",  # a newline would forge a log record
        "bad\r\nX-Evil: 1",  # and a header
        "\x00\x01",  # control characters corrupt the response header
    ],
)
def test_hostile_client_ids_are_reduced_to_something_safe(raw: str) -> None:
    cleaned = sanitize_trace_id(raw)
    assert "\n" not in cleaned and "\r" not in cleaned
    assert cleaned.isprintable()
    assert cleaned


def test_overlong_client_id_is_capped() -> None:
    assert len(sanitize_trace_id("a" * 500)) == 64


def test_blank_client_id_falls_back_to_a_fresh_one() -> None:
    assert sanitize_trace_id("") not in ("", "-")
    assert sanitize_trace_id("   ") not in ("", "-")
    assert sanitize_trace_id(None) not in ("", "-")
