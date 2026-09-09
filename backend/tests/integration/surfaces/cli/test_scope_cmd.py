"""Integration tests for `coffer scope ...` CLI subcommands (ADR-045).

Reuses the shared ``in_proc_daemon`` fixture (see conftest.py), which wires
``fake_scoped`` (supports_scope=True, mirrors mcp_server/skill) alongside the
plain ``fake_kind`` (no scope support, mirrors agent/channel/knowledge_base/
memory) used by test_resource_cmd.py.

Setup/assertions talk to the resource-scope HTTP routes directly via the
monkeypatched client (bypassing the CLI, like test_resource_cmd.py's
``_register`` helper) so each test only exercises the CLI surface under
test through ``coffer scope ...`` itself.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.main import app as cli_app

_runner = CliRunner()


def _register(kind: str, name: str) -> None:
    client, _info = _cli_client.client_or_exit()
    r = client.post("/resources", json={"kind": kind, "name": name, "config": {}})
    assert r.status_code == 201, r.text


def _get_scope(kind: str, name: str) -> dict:
    client, _info = _cli_client.client_or_exit()
    r = client.get(f"/resources/{kind}/{name}/scope")
    assert r.status_code == 200, r.text
    return r.json()


def _put_scope(kind: str, name: str, scope: object) -> None:
    client, _info = _cli_client.client_or_exit()
    r = client.put(f"/resources/{kind}/{name}/scope", json={"scope": scope})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# scope show
# ---------------------------------------------------------------------------


def test_scope_show_happy_path(in_proc_daemon):
    _register("fake_scoped", "w1")
    result = _runner.invoke(cli_app, ["scope", "show", "fake_scoped:w1"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["scope"] is None
    assert body["supports_scope"] is True


def test_scope_show_reports_kinds_without_scope(in_proc_daemon):
    client, _info = _cli_client.client_or_exit()
    r = client.post("/resources", json={"kind": "fake_kind", "name": "n1", "config": {"foo": 1}})
    assert r.status_code == 201, r.text
    result = _runner.invoke(cli_app, ["scope", "show", "fake_kind:n1"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["scope"] is None
    assert body["supports_scope"] is False


def test_scope_show_reflects_current_scope(in_proc_daemon):
    _register("fake_scoped", "w1")
    _put_scope("fake_scoped", "w1", ["claude-code", "codex"])
    result = _runner.invoke(cli_app, ["scope", "show", "fake_scoped:w1"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["scope"] == ["claude-code", "codex"]


def test_scope_show_bad_ref_exit_2(in_proc_daemon):
    result = _runner.invoke(cli_app, ["scope", "show", "noref"])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# scope set
# ---------------------------------------------------------------------------


def test_scope_set_with_agents(in_proc_daemon):
    _register("fake_scoped", "w1")
    result = _runner.invoke(
        cli_app, ["scope", "set", "fake_scoped:w1", "--agents", "claude-code,codex"]
    )
    assert result.exit_code == 0, result.output
    assert _get_scope("fake_scoped", "w1")["scope"] == ["claude-code", "codex"]


def test_scope_set_replaces_the_whole_list(in_proc_daemon):
    _register("fake_scoped", "w1")
    _put_scope("fake_scoped", "w1", ["claude-code", "codex"])
    result = _runner.invoke(cli_app, ["scope", "set", "fake_scoped:w1", "--agents", "cursor"])
    assert result.exit_code == 0, result.output
    assert _get_scope("fake_scoped", "w1")["scope"] == ["cursor"]


def test_scope_set_no_agents_is_dormant(in_proc_daemon):
    _register("fake_scoped", "w1")
    result = _runner.invoke(cli_app, ["scope", "set", "fake_scoped:w1", "--no-agents"])
    assert result.exit_code == 0, result.output
    assert _get_scope("fake_scoped", "w1")["scope"] == []
    assert "dormant" in result.output.lower()


def test_scope_set_requires_exactly_one_mode(in_proc_daemon):
    _register("fake_scoped", "w1")
    neither = _runner.invoke(cli_app, ["scope", "set", "fake_scoped:w1"])
    assert neither.exit_code == 2

    both = _runner.invoke(
        cli_app, ["scope", "set", "fake_scoped:w1", "--agents", "codex", "--no-agents"]
    )
    assert both.exit_code == 2


def test_scope_set_empty_agents_list_exit_2(in_proc_daemon):
    """`--agents ","` (no actual names) must not silently PUT a dormant scope."""
    _register("fake_scoped", "w1")
    result = _runner.invoke(cli_app, ["scope", "set", "fake_scoped:w1", "--agents", ","])
    assert result.exit_code == 2
    assert _get_scope("fake_scoped", "w1")["scope"] is None


def test_scope_set_on_kind_without_scope_fails(in_proc_daemon):
    client, _info = _cli_client.client_or_exit()
    r = client.post("/resources", json={"kind": "fake_kind", "name": "n2", "config": {"foo": 1}})
    assert r.status_code == 201, r.text
    result = _runner.invoke(cli_app, ["scope", "set", "fake_kind:n2", "--agents", "codex"])
    assert result.exit_code != 0


def test_scope_set_bad_ref_exit_2(in_proc_daemon):
    result = _runner.invoke(cli_app, ["scope", "set", "noref", "--agents", "codex"])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# scope clear
# ---------------------------------------------------------------------------


def test_scope_clear_restores_active_for_every_agent(in_proc_daemon):
    _register("fake_scoped", "w1")
    _put_scope("fake_scoped", "w1", ["claude-code"])
    result = _runner.invoke(cli_app, ["scope", "clear", "fake_scoped:w1"])
    assert result.exit_code == 0, result.output
    assert _get_scope("fake_scoped", "w1")["scope"] is None
    assert "every agent" in result.output.lower()


def test_scope_clear_from_dormant(in_proc_daemon):
    _register("fake_scoped", "w1")
    _put_scope("fake_scoped", "w1", [])
    result = _runner.invoke(cli_app, ["scope", "clear", "fake_scoped:w1"])
    assert result.exit_code == 0, result.output
    assert _get_scope("fake_scoped", "w1")["scope"] is None


def test_scope_clear_bad_ref_exit_2(in_proc_daemon):
    result = _runner.invoke(cli_app, ["scope", "clear", "noref"])
    assert result.exit_code == 2
