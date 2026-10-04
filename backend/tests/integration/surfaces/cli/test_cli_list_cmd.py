"""`coffer cli list`: an agent reads the command-line tools Coffer manages.

Spec skill-manager "Serve required commands on REST and the web". Runs the
Typer app in process against a mocked daemon; nothing is started or written.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.main import app

_runner = CliRunner()

_ITEMS: list[dict[str, Any]] = [
    {
        "command": "gh",
        "title": None,
        "description": None,
        "added": False,
        "status": "missing",
        "version": None,
        "needed_by": [{"skill_name": "submitting-review"}],
        "needed_by_servers": [],
    },
    {
        "command": "uv",
        "title": None,
        "description": None,
        "added": False,
        "status": "ready",
        "version": "0.8.0",
        "needed_by": [],
        "needed_by_servers": [{"server_name": "duckdb", "launcher": "uvx"}],
    },
    {
        "command": "jq",
        "title": "JSON",
        "description": "Slice API responses",
        "added": True,
        "status": "ready",
        "version": "1.7.1",
        "needed_by": [],
        "needed_by_servers": [],
    },
]


def _daemon(monkeypatch: pytest.MonkeyPatch, seen: list[tuple[str, str]]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json={"items": _ITEMS, "warnings": []})

    def fresh() -> tuple[httpx.Client, object]:
        client = httpx.Client(
            base_url="http://daemon.invalid/api/v1", transport=httpx.MockTransport(handler)
        )
        return client, object()

    monkeypatch.setattr(_cli_client, "client_or_exit", fresh)


@pytest.mark.acceptance(
    spec="skill-manager", scenario="an agent lists the command-line tools Coffer manages"
)
def test_cli_list_reads_every_managed_tool_without_checking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, str]] = []
    _daemon(monkeypatch, seen)

    result = _runner.invoke(app, ["cli", "list"], env={"COLUMNS": "200"})

    assert result.exit_code == 0, result.output
    out = result.output
    # Problems first, as the daemon ordered them.
    assert out.index("gh") < out.index("uv") < out.index("jq")
    assert "missing" in out
    assert "skill submitting-review" in out
    assert "MCP server duckdb" in out
    assert "added by hand" in out
    assert "JSON — Slice API responses" in out
    # One read; no check ran.
    assert seen == [("GET", "/api/v1/clis")]

    as_json = _runner.invoke(app, ["cli", "list", "--json"])
    assert as_json.exit_code == 0
    assert json.loads(as_json.output) == {"items": _ITEMS}
