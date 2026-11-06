"""Testing a custom tool request before its group is saved, how a failed test
says what went wrong, and what a re-import preview reports as changed
(spec mcp-gateway), against a real daemon and a fake HTTP API.
"""

from __future__ import annotations

import json
import pathlib
import socket
from collections.abc import Iterator
from typing import Any

import pytest

from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon
from tests.support.custom_tools import SECRET_VALUE, create_group, tool
from tests.support.fake_http_api import FakeHttpApi, fake_http_api


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


@pytest.fixture
def api() -> Iterator[FakeHttpApi]:
    with fake_http_api() as a:
        yield a


def _allow_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fake API listens on 127.0.0.1, which the SSRF guard refuses; a test
    that is about the request itself lets it through."""
    monkeypatch.setattr("coffer.infrastructure.mcp.http_api_runner.check_url", lambda url: url)


def _unsaved(d: BoundaryDaemon, base_url: str, **extra: Any) -> dict[str, Any]:
    body = {
        "base_url": base_url,
        "tool": tool("health", "GET", "/services/{service}/health"),
        "arguments": {"service": "web"},
        **extra,
    }
    r = d.client.post("/api/v1/custom-tools/test", json=body)
    assert r.status_code == 200, r.text
    return dict(r.json())


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a request of an unsaved group is tested without its secret"
)
def test_a_request_of_an_unsaved_group_is_tested_without_its_secret(
    daemon: BoundaryDaemon, api: FakeHttpApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_loopback(monkeypatch)
    out = _unsaved(
        daemon,
        api.base_url,
        headers=[
            {"name": "Accept", "value": "application/json"},
            {"name": "Authorization", "secret": "billing-token"},
        ],
    )
    assert out["ok"] is True and out["status"] == 200 and out["failure"] is None
    seen = api.seen[-1]
    assert seen.path == "/services/web/health"
    assert seen.headers["accept"] == "application/json"
    assert "authorization" not in seen.headers
    assert daemon.client.get("/api/v1/custom-tools").json()["groups"] == []


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="an unsaved group on a private address is not tested"
)
def test_an_unsaved_group_on_a_private_address_is_not_tested(
    daemon: BoundaryDaemon, api: FakeHttpApi
) -> None:
    out = _unsaved(daemon, api.base_url)
    assert out["ok"] is False and out["failure"] == "blocked"
    assert "SSRF" in out["error"]
    assert api.seen == []


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a failed test says how it failed")
def test_a_failed_test_says_how_it_failed(
    daemon: BoundaryDaemon, api: FakeHttpApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_loopback(monkeypatch)
    closed = _unsaved(daemon, f"http://127.0.0.1:{_free_port()}")
    assert closed["ok"] is False and closed["failure"] == "connect"
    assert closed["status"] is None
    # No connection depends on this machine: the daemon hands it to an agent.
    assert "could not connect" in closed["handoff"]["prompt"]
    assert "127.0.0.1" in closed["handoff"]["prompt"]
    broken = daemon.client.post(
        "/api/v1/custom-tools/test",
        json={"base_url": api.base_url, "tool": tool("t", "GET", "/{missing}"), "arguments": {}},
    ).json()
    assert broken["failure"] == "request" and broken["handoff"] is None
    create_group(daemon, "billing", api.base_url, [tool("keep", "GET", "/keep")])
    answered = daemon.client.post(
        "/api/v1/custom-tools/billing/test", json={"tool": tool("k", "GET", "/keep")}
    ).json()
    assert answered["failure"] is None and answered["status"] == 200
    assert answered["handoff"] is None
    assert SECRET_VALUE not in json.dumps(answered)
