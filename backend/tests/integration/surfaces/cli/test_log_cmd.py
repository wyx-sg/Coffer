"""``coffer log audit|mcp|daemon`` over the routes the Activity page reads.

``log prune`` is exercised with its retention key in ``test_config_cmd``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.log_cmd import since_instant
from coffer.surfaces.cli.main import app
from tests.integration.surfaces.cli.test_activity_cli_readers import _seed_rows
from tests.integration.surfaces.cli.test_mcp_cmd import (  # noqa: F401  (fixture import)
    _register_server,
    mcp_daemon,
)

_runner = CliRunner()


def _run(*args: str) -> Any:
    return _runner.invoke(app, list(args), env={"COLUMNS": "250"})


def _client() -> Any:
    client, _info = _cli_client.client_or_exit()
    return client


# --- log audit --------------------------------------------------------------------


@pytest.mark.acceptance(spec="resource-framework", scenario="the command line reads the audit log")
def test_the_command_line_reads_the_audit_log(in_proc_daemon: Any) -> None:
    c = _client()
    first = c.post("/resources", json={"kind": "fake_kind", "name": "one", "config": {"foo": 1}})
    second = c.post("/resources", json={"kind": "fake_scoped", "name": "two", "config": {}})
    assert first.status_code == second.status_code == 201
    assert c.post(f"/resources/{first.json()['uid']}/disable").status_code == 200
    assert (
        c.patch(f"/resources/{second.json()['uid']}", json={"description": "retitled"}).status_code
        == 200
    )

    latest = _run("log", "audit", "--limit", "2")
    assert latest.exit_code == 0, latest.output
    rows = [line for line in latest.output.splitlines() if "resource_" in line]
    assert len(rows) == 2
    assert "resource_updated" in rows[0] and "fake_scoped:two" in rows[0]
    assert "resource_disabled" in rows[1] and "fake_kind:one" in rows[1]
    assert all(" api " in f" {row} " for row in rows)

    only_kind = _run("log", "audit", "--kind", "fake_kind", "--json")
    assert only_kind.exit_code == 0, only_kind.output
    entries = json.loads(only_kind.output)["audit_events"]
    assert entries and {e["resource_kind"] for e in entries} == {"fake_kind"}
    assert [e["event_type"] for e in entries] == ["resource_disabled", "resource_created"]


def test_log_audit_name_needs_a_kind(in_proc_daemon: Any) -> None:
    assert _run("log", "audit", "--name", "one").exit_code == 2


# --- log mcp ------------------------------------------------------------------------


@pytest.mark.acceptance(spec="mcp-gateway", scenario="the command line reads the invocation log")
def test_the_command_line_reads_the_invocation_log(mcp_daemon: Any) -> None:  # noqa: F811
    fs = _register_server("fs")
    git = _register_server("git")
    _seed_rows(
        [
            (fs, "read_file", "ok"),
            (fs, "write_file", "error"),
            (git, "git_log", "error"),
            ("coffer", "coffer__write", "error"),
            ("deleted:old", "gone_tool", "error"),
        ]
    )

    one = _run("log", "mcp", "--server", "fs", "--json")
    assert one.exit_code == 0, one.output
    assert [r["capability_key"] for r in json.loads(one.output)["invocations"]] == [
        "write_file",
        "read_file",
    ]
    table = _run("log", "mcp", "--server", "fs")
    assert "read_file" in table.output and "git_log" not in table.output

    failed = _run("log", "mcp", "--status", "error", "--json")
    assert failed.exit_code == 0, failed.output
    rows = json.loads(failed.output)["invocations"]
    assert {r["status"] for r in rows} == {"error"}
    assert {r["resource_uid"] for r in rows} == {fs, git, "coffer", "deleted:old"}


@pytest.mark.acceptance(spec="web-ui", scenario="the command-line readers still read the records")
def test_every_record_reader_runs(
    mcp_daemon: Any,  # noqa: F811
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COFFER_LOG_DIR", str(tmp_path / "logs"))
    _write_log(tmp_path / "logs", [_line(datetime.now(tz=UTC), "info", "one record")])
    fs = _register_server("fs")
    _seed_rows([(fs, "read_file", "ok"), ("coffer", "coffer__write", "ok")])

    for args in (["mcp", "--server", "fs"], ["mcp"], ["daemon"]):
        result = _run("log", *args, "--json")
        assert result.exit_code == 0, (args, result.output)
        json.loads(result.output)
    assert "coffer__write" in _run("log", "mcp").output


# --- log daemon ------------------------------------------------------------------------


_TRACEBACK = 'Traceback (most recent call last):\n  File "x.py", line 1\nValueError: boom'


def _line(at: datetime, level: str, event: str, **extra: Any) -> str:
    stamp = at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return json.dumps(
        {"timestamp": stamp, "level": level, "logger": "coffer.test", "event": event, **extra}
    )


def _write_log(directory: Any, lines: list[str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "daemon.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.mark.acceptance(spec="daemon", scenario="the command line reads the daemon log tail")
def test_the_command_line_reads_the_daemon_log_tail(
    in_proc_daemon: Any, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(tz=UTC)
    monkeypatch.setenv("COFFER_LOG_DIR", str(tmp_path / "logs"))
    _write_log(
        tmp_path / "logs",
        [
            _line(now - timedelta(hours=3), "info", "long ago"),
            _line(now - timedelta(minutes=10), "info", "recent info"),
            _line(
                now - timedelta(minutes=5),
                "error",
                "it broke",
                exception=_TRACEBACK,
            ),
        ],
    )

    window = _run("log", "daemon", "--json", "--since", "1h")
    assert window.exit_code == 0, window.output
    records = json.loads(window.output)["records"]
    assert [r["event"] for r in records] == ["it broke", "recent info"]
    direct = _client().get("/daemon/logs", params={"since": since_instant("1h")}).json()
    assert [r["event"] for r in direct["records"]] == [r["event"] for r in records]

    errors = _run("log", "daemon", "--errors", "--limit", "1")
    assert errors.exit_code == 0, errors.output
    assert "it broke" in errors.output and "recent info" not in errors.output
    assert "ValueError: boom" in errors.output


def test_since_takes_an_age_or_an_instant() -> None:
    now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    assert since_instant("1h", now=now) == "2026-09-28T11:00:00+00:00"
    assert since_instant("2d", now=now) == "2026-09-26T12:00:00+00:00"
    assert since_instant("2026-09-01T00:00:00+00:00") == "2026-09-01T00:00:00+00:00"
    assert since_instant(None) is None


def test_a_malformed_since_is_a_usage_error(in_proc_daemon: Any) -> None:
    assert _run("log", "daemon", "--since", "yesterday").exit_code == 2
