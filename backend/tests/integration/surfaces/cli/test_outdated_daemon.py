"""The CLI against a daemon older than itself.

A daemon started before the experimental-features change answers
``/daemon/status`` without ``channel`` and without ``machine_id``. The CLI says
that the daemon needs a restart, rather than failing on a missing key or
telling the user to try again — which no amount of trying would change.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

import coffer.surfaces.cli._client as cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app

runner = CliRunner()

_OLD_STATUS: dict[str, Any] = {"status": "ok", "version": "0.4.0"}
_RESTART = "coffer daemon restart"


class _FakeDaemon:
    """Answers each path from a table, the way the routes the CLI reads would."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self._answers = answers
        self.base_url = "http://localhost/api/v1"

    def __enter__(self) -> _FakeDaemon:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def request(self, method: str, url: str, **_kw: Any) -> httpx.Response:
        request = httpx.Request(method, "http://localhost/api/v1" + url)
        return httpx.Response(200, json=self._answers[url], request=request)

    def get(self, url: str, **kw: Any) -> httpx.Response:
        return self.request("GET", url, **kw)

    def put(self, url: str, **kw: Any) -> httpx.Response:
        return self.request("PUT", url, **kw)

    def patch(self, url: str, **kw: Any) -> httpx.Response:
        return self.request("PATCH", url, **kw)


def _serve(monkeypatch: pytest.MonkeyPatch, answers: dict[str, Any]) -> None:
    info = DaemonInfo(
        version=1,
        pid=4242,
        port=59790,
        token="t",
        started_at=datetime.now(tz=UTC),
        binary_path="/test",
    )
    monkeypatch.setattr(cli_client, "client_or_exit", lambda: (_FakeDaemon(answers), info))


def test_daemon_status_names_an_outdated_daemon_instead_of_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, {"/daemon/status": _OLD_STATUS})
    res = runner.invoke(app, ["daemon", "status"])
    assert res.exit_code == 0, res.output
    [line] = [line for line in res.output.splitlines() if line.startswith("channel:")]
    assert "unknown" in line
    assert _RESTART in line


_CHANNEL_ROWS = {
    "/resources": {"resources": [{"uid": "ch-1", "name": "tg", "kind": "channel"}]},
    "/resources/ch-1": {"uid": "ch-1", "name": "tg", "config": {}},
}


def test_channel_bind_names_an_outdated_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, {**_CHANNEL_ROWS, "/daemon/status": _OLD_STATUS})
    res = runner.invoke(app, ["channel", "bind", "tg"])
    assert res.exit_code == 1, res.output
    assert "predates this CLI" in res.output
    assert _RESTART in res.output
    assert "try again" not in res.output


def test_channel_bind_asks_for_a_retry_while_the_id_is_not_derived(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The key is there and empty: a current daemon that has not derived the
    id yet — the one case where trying again is the right advice."""
    _serve(monkeypatch, {**_CHANNEL_ROWS, "/daemon/status": {**_OLD_STATUS, "machine_id": None}})
    res = runner.invoke(app, ["channel", "bind", "tg"])
    assert res.exit_code == 1, res.output
    assert "try again" in res.output


def test_curate_owner_names_an_outdated_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(
        monkeypatch,
        {
            "/internal-engine-config": {"curate_owner_machine_id": None},
            "/daemon/status": _OLD_STATUS,
        },
    )
    res = runner.invoke(app, ["engine", "curate-owner", "show"])
    assert res.exit_code == 1, res.output
    assert _RESTART in res.output
