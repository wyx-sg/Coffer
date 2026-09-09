"""Integration: `coffer memory merge-scan` / `coffer memory merge` (FR-056/057).

Mirrors ``test_memory_cmd.py``: full app via ``create_app``, CLI client routed
to a Starlette ``TestClient``. The test env has no internal engine, so the
scan degrades to ``no_model`` (the engine tier itself is unit-tested)."""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime as dt

import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_runner = CliRunner()
_TOKEN = "test-token-memory-merge-cli"
_SRC = "project-" + "B" * 26
_DST = "project-" + "A" * 26


def _extract_json(output: str) -> str:
    lines = output.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line and line[0] in "[{":
            return "".join(lines[i:])
    return output


@pytest.fixture
def merge_cli_daemon(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59810")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59819")
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))

    app = create_app()
    set_active_token(_TOKEN)
    info = DaemonInfo(
        version=1,
        pid=12345,
        port=59810,
        token=_TOKEN,
        started_at=dt.now(tz=UTC),
        binary_path="/test",
    )
    fake_client = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN, "X-Coffer-Actor": "cli"},
        raise_server_exceptions=False,
    )
    fake_client.__enter__()

    class _PersistentClient:
        def __init__(self, inner: TestClient) -> None:
            self._inner = inner

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return None

        def __getattr__(self, item):  # type: ignore[no-untyped-def]
            return getattr(self._inner, item)

    monkeypatch.setattr(
        _cli_client,
        "client_or_exit",
        lambda: (_PersistentClient(fake_client), info),
    )
    yield fake_client
    fake_client.__exit__(None, None, None)


def _add_fact(c: TestClient, store: str, text: str) -> None:
    r = c.post(f"/memory_stores/{store}/facts", json={"title": text, "text": text})
    assert r.status_code == 201, r.text


def test_merge_scan_json_reports_no_model(merge_cli_daemon):
    result = _runner.invoke(cli_app, ["memory", "merge-scan", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(_extract_json(result.output))
    assert data["engine"] == "no_model"
    assert data["proposals"] == []


def test_merge_scan_table_reports_no_candidates(merge_cli_daemon):
    result = _runner.invoke(cli_app, ["memory", "merge-scan"])
    assert result.exit_code == 0, result.output
    assert "no merge candidates found" in result.output
    assert "no internal engine configured" in result.output


def test_merge_happy_path_human_summary(merge_cli_daemon):
    _add_fact(merge_cli_daemon, _SRC, "src fact")
    _add_fact(merge_cli_daemon, _DST, "dst fact")
    result = _runner.invoke(cli_app, ["memory", "merge", _SRC, _DST, "--no-organize"])
    assert result.exit_code == 0, result.output
    assert f"merged {_SRC} into {_DST}" in result.output
    assert "organize: skipped" in result.output

    listing = _runner.invoke(cli_app, ["memory", "list", "--json"])
    names = [s["name"] for s in json.loads(_extract_json(listing.output))["memory_stores"]]
    assert _SRC not in names and _DST in names


def test_merge_json_output_carries_aliases(merge_cli_daemon):
    _add_fact(merge_cli_daemon, _SRC, "src fact")
    _add_fact(merge_cli_daemon, _DST, "dst fact")
    result = _runner.invoke(cli_app, ["memory", "merge", _SRC, _DST, "--no-organize", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(_extract_json(result.output))
    assert data["target"] == _DST
    assert data["aliases"] == ["B" * 26]
    assert data["reorg_status"] == "skipped"


def test_merge_invalid_pair_exits_nonzero(merge_cli_daemon):
    result = _runner.invoke(cli_app, ["memory", "merge", "global", _DST])
    assert result.exit_code != 0
