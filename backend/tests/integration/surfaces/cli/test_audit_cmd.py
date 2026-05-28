"""Integration tests for `coffer audit` CLI subcommands."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from coffer.surfaces.cli.main import app

_runner = CliRunner()


def _register_and_act(in_proc_daemon, name: str = "r1") -> None:
    """Register a resource to generate audit entries."""
    from coffer.surfaces.cli import _client as _cli_client

    client, _info = _cli_client.client_or_exit()
    r = client.post(
        "/resources",
        json={"kind": "fake_kind", "name": name, "config": {"foo": 1}},
    )
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# audit list
# ---------------------------------------------------------------------------


def test_audit_list_empty(in_proc_daemon):
    result = _runner.invoke(app, ["audit", "list", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    # Stable top-level key per spec scenario: `audit_events` for `audit list`.
    assert isinstance(payload, dict)
    assert "audit_events" in payload
    assert isinstance(payload["audit_events"], list)


def test_audit_list_shows_entries_after_action(in_proc_daemon):
    _register_and_act(in_proc_daemon)
    result = _runner.invoke(app, ["audit", "list", "--json"])
    assert result.exit_code == 0, result.output
    entries = json.loads(result.output)["audit_events"]
    assert len(entries) >= 1
    # Expect a registered event
    event_types = [e["event_type"] for e in entries]
    assert any("register" in et.lower() or "create" in et.lower() for et in event_types)


def test_audit_list_filter_kind(in_proc_daemon):
    _register_and_act(in_proc_daemon)
    result = _runner.invoke(app, ["audit", "list", "--kind", "fake_kind", "--json"])
    assert result.exit_code == 0
    entries = json.loads(result.output)["audit_events"]
    # All returned entries should be for fake_kind
    for e in entries:
        assert e.get("resource_kind") == "fake_kind"


def test_audit_list_limit(in_proc_daemon):
    for i in range(5):
        _register_and_act(in_proc_daemon, name=f"r{i}")
    result = _runner.invoke(app, ["audit", "list", "--limit", "2", "--json"])
    assert result.exit_code == 0
    entries = json.loads(result.output)["audit_events"]
    assert len(entries) <= 2


def test_audit_list_table_output(in_proc_daemon):
    """Default (non-JSON) output should produce a table."""
    result = _runner.invoke(app, ["audit", "list"])
    assert result.exit_code == 0, result.output
    # Rich table contains "Audit Log" header
    assert "Audit" in result.output
