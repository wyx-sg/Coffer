"""``coffer mcp prompt`` and ``coffer mcp test --prompt``: the CLI prints the
hand-off the routes serve, as served (spec mcp-gateway "Name a missing stdio
launcher", "Hand a failing MCP server's diagnosis to an agent")."""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli import _client as cli_client
from coffer.surfaces.cli import mcp as mcp_cli
from coffer.surfaces.cli.main import app as cli

runner = CliRunner()

PROMPT = "Please find out why the MCP server jira, which Coffer runs for my agents, fails."


class _Response:
    def __init__(self, body: dict[str, Any], status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self._body


class _Client:
    def __init__(self, routes: dict[str, dict[str, Any]]) -> None:
        self.routes = routes

    def __enter__(self) -> _Client:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def get(self, path: str) -> _Response:
        return _Response(self.routes[path])

    def post(self, path: str) -> _Response:
        return _Response(self.routes[path])


def _serve(monkeypatch: pytest.MonkeyPatch, routes: dict[str, dict[str, Any]]) -> None:
    monkeypatch.setattr(cli_client, "client_or_exit", lambda: (_Client(routes), None))
    monkeypatch.setattr(cli_client, "check", lambda *_a, **_k: None)
    monkeypatch.setattr(mcp_cli, "resolve_uid", lambda _c, _kind, name, **_k: f"u-{name}")


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="coffer mcp prompt prints the server's hand-off"
)
def test_prompt_prints_the_status_hand_off_or_exits_5(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(
        monkeypatch,
        {
            "/resources/mcp_server/u-jira/status": {
                "status": "failing",
                "handoff": {"prompt": PROMPT},
            },
            "/resources/mcp_server/u-fine/status": {"status": "healthy", "handoff": None},
        },
    )
    printed = runner.invoke(cli, ["mcp", "prompt", "jira"])
    assert printed.exit_code == 0, printed.output
    assert printed.stdout == PROMPT + "\n"
    nothing = runner.invoke(cli, ["mcp", "prompt", "fine"])
    assert nothing.exit_code == 5
    assert "nothing handed off" in (nothing.stderr or nothing.output)


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="coffer mcp test prints the diagnosis with --prompt"
)
def test_test_points_at_prompt_and_prints_it_with_the_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    failed = {
        "ok": False,
        "latency_ms": 40,
        "error_message": "exited with status 1",
        "handoff": {"prompt": PROMPT},
    }
    _serve(
        monkeypatch,
        {
            "/resources/mcp_server/u-jira/refresh": {"tools": [], "prompts": [], "resources": []},
            "/resources/mcp_server/u-jira/test": failed,
        },
    )
    plain = runner.invoke(cli, ["mcp", "test", "jira"])
    assert plain.exit_code == 7
    assert "coffer mcp test jira --prompt" in plain.stderr
    assert PROMPT not in plain.stdout
    flagged = runner.invoke(cli, ["mcp", "test", "jira", "--prompt"])
    assert flagged.exit_code == 7
    assert flagged.stdout.endswith(PROMPT + "\n")
