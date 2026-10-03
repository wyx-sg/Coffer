"""``coffer proxy token``: what an agent's key helper runs (spec
provider-switching "Authenticate each agent to the proxy with its own local
token")."""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli import _client as cli_client
from coffer.surfaces.cli.main import app as cli

runner = CliRunner()
UID = "a" * 32
TOKEN = "cfr_" + "x" * 48


class _Response:
    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict[str, Any]:
        return self._body

    def raise_for_status(self) -> None:
        return None


class _Client:
    def __enter__(self) -> _Client:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def get(self, path: str) -> _Response:
        if path == f"/proxy/tokens/{UID}":
            return _Response(200, {"token": TOKEN})
        return _Response(404, {})


@pytest.fixture(autouse=True)
def served(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_client, "client_or_exit", lambda: (_Client(), None))


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="the token command prints a local token, never a provider key",
)
def test_proxy_token_prints_only_the_local_token() -> None:
    r = runner.invoke(cli, ["proxy", "token", "--agent-uid", UID])
    assert r.exit_code == 0, r.output
    assert r.output == TOKEN + "\n"

    missing = runner.invoke(cli, ["proxy", "token", "--agent-uid", "0" * 32])
    assert missing.exit_code == 4
    assert missing.stdout == ""
