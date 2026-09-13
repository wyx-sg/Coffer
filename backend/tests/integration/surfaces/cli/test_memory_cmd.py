"""Integration tests for ``coffer memory ...`` (spec memory FR-061).

Most commands are thin HTTP shells, tested the same way
``test_knowledge_cmd.py`` tests its own: boot the real app, route
``_cli_client.client_or_exit`` at a ``TestClient`` over it. ``context`` is
different on purpose (see its own docstring in ``memory_cmd.py``) — it never
goes through ``client_or_exit``'s detect-or-spawn, so it is tested by
monkeypatching ``live_daemon``/``httpx.post`` directly, proving the "never
fail a session" contract even when nothing is listening at all.
"""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime as dt

import httpx
import pytest
from starlette.testclient import TestClient
from typer.testing import CliRunner

import coffer.surfaces.cli._client as _cli_client
import coffer.surfaces.cli.memory_cmd as memory_cmd
from coffer.infrastructure.daemon.pid_lock import DaemonInfo
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

_runner = CliRunner()
_TOKEN = "test-token-memory-cli"

_CC_PROJECT_FACT = """---
name: python-lockfile
description: Dependencies are locked with uv
metadata:
  type: project
---

Run `uv sync --frozen` in this project; a plain `pip install` drifts.
"""


def _extract_json(output: str) -> str:
    lines = output.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line and line[0] in "[{":
            return "".join(lines[i:])
    return output


def _encode(name: str) -> str:
    return "".join(ch if ch.isalnum() and ch.isascii() else "-" for ch in name)


def _cc_slug(project_root) -> str:
    parts = [p for p in project_root.parts if p != "/"]
    return "-" + "-".join(_encode(p) for p in parts)


@pytest.fixture
def memory_cli_daemon(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", "59900")
    monkeypatch.setenv("COFFER_PORT_RANGE_END", "59909")
    monkeypatch.setenv("COFFER_MEMORY_ROOT", str(tmp_path / "memory"))
    monkeypatch.setenv("COFFER_KNOWLEDGE_ROOT", str(tmp_path / "knowledge"))
    monkeypatch.setenv("COFFER_INDEX_ROOT", str(tmp_path / "index"))
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)

    app = create_app()
    set_active_token(_TOKEN)

    info = DaemonInfo(
        version=1,
        pid=12345,
        port=59900,
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
        _cli_client, "client_or_exit", lambda: (_PersistentClient(fake_client), info)
    )
    yield tmp_path
    fake_client.__exit__(None, None, None)


def _register_cc_via_http(tmp_path):
    """Register the agent directly through the fake client (sidesteps any
    ``coffer agent`` CLI verb naming this suite does not need to pin down)."""
    c, _info = _cli_client.client_or_exit()
    with c:
        r = c.post("/agents", json={"type": "claude_code", "name": "cc"})
        assert r.status_code == 201, r.text


def _write_cc_fact(tmp_path) -> None:
    project_root = tmp_path / "proj"
    project_root.mkdir(parents=True, exist_ok=True)
    memory_dir = tmp_path / ".claude" / "projects" / _cc_slug(project_root) / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "python-lockfile.md").write_text(_CC_PROJECT_FACT, encoding="utf-8")


def test_sync_then_partitions_and_facts(memory_cli_daemon):
    tmp_path = memory_cli_daemon
    _register_cc_via_http(tmp_path)
    _write_cc_fact(tmp_path)

    synced = _runner.invoke(cli_app, ["memory", "sync", "--json"])
    assert synced.exit_code == 0, synced.output
    result = json.loads(_extract_json(synced.output))
    assert result["facts_written"] == 1

    listed = _runner.invoke(cli_app, ["memory", "partitions", "--json"])
    assert listed.exit_code == 0, listed.output
    partitions = json.loads(_extract_json(listed.output))["partitions"]
    project = next(p for p in partitions if p["name"] != "global")

    facts = _runner.invoke(cli_app, ["memory", "facts", project["name"], "--json"])
    assert facts.exit_code == 0, facts.output
    fact = json.loads(_extract_json(facts.output))["facts"][0]
    assert fact["title"] == "python-lockfile"

    shown = _runner.invoke(cli_app, ["memory", "fact", project["name"], fact["slug"]])
    assert shown.exit_code == 0, shown.output
    assert "uv sync --frozen" in shown.output


@pytest.mark.acceptance(spec="memory", scenario="a hidden fact stays hidden across a rebuild")
def test_hide_survives_a_rebuild_via_cli(memory_cli_daemon):
    import shutil

    tmp_path = memory_cli_daemon
    _register_cc_via_http(tmp_path)
    _write_cc_fact(tmp_path)
    _runner.invoke(cli_app, ["memory", "sync"])

    partitions = json.loads(
        _extract_json(_runner.invoke(cli_app, ["memory", "partitions", "--json"]).output)
    )["partitions"]
    project = next(p for p in partitions if p["name"] != "global")
    facts = json.loads(
        _extract_json(
            _runner.invoke(cli_app, ["memory", "facts", project["name"], "--json"]).output
        )
    )["facts"]
    key = facts[0]["key"]

    hidden = _runner.invoke(cli_app, ["memory", "hide", key])
    assert hidden.exit_code == 0, hidden.output

    shutil.rmtree(tmp_path / "memory")
    _runner.invoke(cli_app, ["memory", "sync"])

    facts2 = json.loads(
        _extract_json(
            _runner.invoke(cli_app, ["memory", "facts", project["name"], "--json"]).output
        )
    )["facts"]
    assert facts2[0]["key"] == key
    assert facts2[0]["hidden"] is True


def test_overrides_list_and_delivery_round_trip(memory_cli_daemon):
    tmp_path = memory_cli_daemon
    _register_cc_via_http(tmp_path)

    installed = _runner.invoke(cli_app, ["memory", "delivery-install", "cc"])
    assert installed.exit_code == 0, installed.output

    status = _runner.invoke(cli_app, ["memory", "delivery", "--json"])
    data = json.loads(_extract_json(status.output))["delivery"]
    assert any(d["agent"] == "cc" and d["installed"] for d in data)

    removed = _runner.invoke(cli_app, ["memory", "delivery-remove", "cc"])
    assert removed.exit_code == 0, removed.output


# ----- `context`: the hook-invoked command, tested without client_or_exit --


def test_context_prints_nothing_and_exits_zero_when_no_daemon_is_running(monkeypatch):
    monkeypatch.setattr(memory_cmd, "live_daemon", lambda: None)
    result = _runner.invoke(cli_app, ["memory", "context", "--agent", "cc", "--cwd", "/tmp"])
    assert result.exit_code == 0
    assert result.output == ""


def test_context_prints_nothing_and_exits_zero_on_a_network_failure(monkeypatch):
    info = DaemonInfo(
        version=1, pid=1, port=1, token="t", started_at=dt.now(tz=UTC), binary_path="/test"
    )
    monkeypatch.setattr(memory_cmd, "live_daemon", lambda: info)

    def _raise(*args, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(memory_cmd.httpx, "post", _raise)
    result = _runner.invoke(cli_app, ["memory", "context", "--agent", "cc", "--cwd", "/tmp"])
    assert result.exit_code == 0
    assert result.output == ""


def test_context_prints_nothing_on_a_non_200_response(monkeypatch):
    info = DaemonInfo(
        version=1, pid=1, port=1, token="t", started_at=dt.now(tz=UTC), binary_path="/test"
    )
    monkeypatch.setattr(memory_cmd, "live_daemon", lambda: info)
    monkeypatch.setattr(
        memory_cmd.httpx,
        "post",
        lambda *a, **kw: httpx.Response(500, request=httpx.Request("POST", "http://x")),
    )
    result = _runner.invoke(cli_app, ["memory", "context", "--agent", "cc", "--cwd", "/tmp"])
    assert result.exit_code == 0
    assert result.output == ""


def test_context_prints_the_composed_text_and_records_a_fire(memory_cli_daemon, monkeypatch):
    tmp_path = memory_cli_daemon
    _register_cc_via_http(tmp_path)

    info = DaemonInfo(
        version=1, pid=1, port=59900, token=_TOKEN, started_at=dt.now(tz=UTC), binary_path="/test"
    )
    monkeypatch.setattr(memory_cmd, "live_daemon", lambda: info)

    # `context` bypasses `client_or_exit()` and calls `httpx.post` against a
    # real socket (see the module docstring); nothing here binds one, so
    # route that one call at the same in-process app the rest of this suite
    # uses, exactly as `client_or_exit` is monkeypatched above.
    real_client, _ = _cli_client.client_or_exit()

    def _fake_post(url, *, json=None, headers=None, timeout=None):
        path = url.split("/api/v1", 1)[1]
        return real_client.post(path, json=json)

    monkeypatch.setattr(memory_cmd.httpx, "post", _fake_post)

    before = _runner.invoke(cli_app, ["memory", "delivery", "--json"])
    before_data = json.loads(_extract_json(before.output))["delivery"]
    assert next(d for d in before_data if d["agent"] == "cc")["last_fired_at"] == ""

    result = _runner.invoke(cli_app, ["memory", "context", "--agent", "cc", "--cwd", "/tmp"])
    assert result.exit_code == 0, result.output
    assert "Coffer memory" in result.output

    after = _runner.invoke(cli_app, ["memory", "delivery", "--json"])
    after_data = json.loads(_extract_json(after.output))["delivery"]
    assert next(d for d in after_data if d["agent"] == "cc")["last_fired_at"] != ""
