"""A server's status read lists what it requires, against a real daemon
(spec mcp-gateway "Show what an MCP server requires")."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest

from tests.support.boundary_daemon import BoundaryDaemon, prepare_home, running_daemon


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


@pytest.mark.acceptance(spec="mcp-gateway", scenario="a server's page lists what it requires")
def test_the_status_read_lists_the_launcher_and_the_secrets(daemon: BoundaryDaemon):
    daemon.store("secret/notion", "ntn_value")
    server = daemon.register_stdio(
        "notion",
        "no-such-launcher-for-coffer-tests",
        {"NOTION_TOKEN": "secret/notion"},
    )
    r = daemon.client.get(f"/api/v1/resources/mcp_server/{server['uid']}/status")
    assert r.status_code == 200, r.text
    rows = {(x["kind"], x["name"]): x for x in r.json()["requires"]}
    assert rows[("cli", "no-such-launcher-for-coffer-tests")]["status"] == "not_found"
    assert rows[("secret", "NOTION_TOKEN")]["secret"] == "notion"
    assert rows[("secret", "NOTION_TOKEN")]["status"] in ("set", "waiting_approval")
    assert "ntn_value" not in r.text
