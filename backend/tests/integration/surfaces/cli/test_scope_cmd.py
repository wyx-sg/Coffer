"""Integration tests for `coffer scope ...` CLI subcommands (ADR-045, Task 15).

Reuses the shared ``in_proc_daemon`` fixture (see conftest.py), which wires
two scope-capable Kinds specifically for this file: ``fake_scoped``
(machine + agent axes, mirrors mcp_server/skill) and ``fake_machine_only``
(machine axis only, mirrors agent/channel) — alongside the plain
``fake_kind`` (no scope support) used by test_resource_cmd.py.

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
    assert sorted(body["axes"]) == ["agent", "machine"]


def test_scope_show_reflects_current_scope(in_proc_daemon):
    _register("fake_scoped", "w1")
    _put_scope("fake_scoped", "w1", {"m1": ["a", "b"], "m2": "*"})
    result = _runner.invoke(cli_app, ["scope", "show", "fake_scoped:w1"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["scope"] == {"m1": ["a", "b"], "m2": "*"}


def test_scope_show_bad_ref_exit_2(in_proc_daemon):
    result = _runner.invoke(cli_app, ["scope", "show", "noref"])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# scope set
# ---------------------------------------------------------------------------


def test_scope_set_with_agents(in_proc_daemon):
    _register("fake_scoped", "w1")
    result = _runner.invoke(
        cli_app, ["scope", "set", "fake_scoped:w1", "--machine", "m1", "--agents", "a,b"]
    )
    assert result.exit_code == 0, result.output
    assert _get_scope("fake_scoped", "w1")["scope"] == {"m1": ["a", "b"]}


def test_scope_set_with_all_agents(in_proc_daemon):
    _register("fake_scoped", "w1")
    result = _runner.invoke(
        cli_app, ["scope", "set", "fake_scoped:w1", "--machine", "m1", "--all-agents"]
    )
    assert result.exit_code == 0, result.output
    assert _get_scope("fake_scoped", "w1")["scope"] == {"m1": "*"}


def test_scope_set_merges_additional_machine(in_proc_daemon):
    _register("fake_scoped", "w1")
    first = _runner.invoke(
        cli_app, ["scope", "set", "fake_scoped:w1", "--machine", "m1", "--all-agents"]
    )
    assert first.exit_code == 0, first.output
    second = _runner.invoke(
        cli_app, ["scope", "set", "fake_scoped:w1", "--machine", "m2", "--agents", "x"]
    )
    assert second.exit_code == 0, second.output
    assert _get_scope("fake_scoped", "w1")["scope"] == {"m1": "*", "m2": ["x"]}


def test_scope_set_overwrites_same_machine(in_proc_daemon):
    _register("fake_scoped", "w1")
    _put_scope("fake_scoped", "w1", {"m1": ["a"]})
    result = _runner.invoke(
        cli_app, ["scope", "set", "fake_scoped:w1", "--machine", "m1", "--all-agents"]
    )
    assert result.exit_code == 0, result.output
    assert _get_scope("fake_scoped", "w1")["scope"] == {"m1": "*"}


def test_scope_set_requires_exactly_one_mode(in_proc_daemon):
    _register("fake_scoped", "w1")
    neither = _runner.invoke(cli_app, ["scope", "set", "fake_scoped:w1", "--machine", "m1"])
    assert neither.exit_code == 2

    both = _runner.invoke(
        cli_app,
        [
            "scope",
            "set",
            "fake_scoped:w1",
            "--machine",
            "m1",
            "--agents",
            "a",
            "--all-agents",
        ],
    )
    assert both.exit_code == 2


def test_scope_set_empty_agents_list_exit_2(in_proc_daemon):
    """`--agents ","` (no actual names) must not silently PUT a dormant entry."""
    _register("fake_scoped", "w1")
    result = _runner.invoke(
        cli_app, ["scope", "set", "fake_scoped:w1", "--machine", "m1", "--agents", ","]
    )
    assert result.exit_code == 2
    assert _get_scope("fake_scoped", "w1")["scope"] is None


def test_scope_set_machine_only_rejects_agents(in_proc_daemon):
    _register("fake_machine_only", "b1")
    result = _runner.invoke(
        cli_app,
        ["scope", "set", "fake_machine_only:b1", "--machine", "m1", "--agents", "a,b"],
    )
    assert result.exit_code == 2


def test_scope_set_machine_only_implies_all_agents(in_proc_daemon):
    _register("fake_machine_only", "b1")
    result = _runner.invoke(cli_app, ["scope", "set", "fake_machine_only:b1", "--machine", "m1"])
    assert result.exit_code == 0, result.output
    assert _get_scope("fake_machine_only", "b1")["scope"] == {"m1": "*"}


def test_scope_set_machine_only_explicit_all_agents_ok(in_proc_daemon):
    _register("fake_machine_only", "b1")
    result = _runner.invoke(
        cli_app, ["scope", "set", "fake_machine_only:b1", "--machine", "m1", "--all-agents"]
    )
    assert result.exit_code == 0, result.output
    assert _get_scope("fake_machine_only", "b1")["scope"] == {"m1": "*"}


def test_scope_set_bad_ref_exit_2(in_proc_daemon):
    result = _runner.invoke(cli_app, ["scope", "set", "noref", "--machine", "m1", "--all-agents"])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# scope clear
# ---------------------------------------------------------------------------


def test_scope_clear_one_entry_leaves_others(in_proc_daemon):
    _register("fake_scoped", "w1")
    _put_scope("fake_scoped", "w1", {"m1": ["a"], "m2": "*"})
    result = _runner.invoke(cli_app, ["scope", "clear", "fake_scoped:w1", "--machine", "m1"])
    assert result.exit_code == 0, result.output
    assert _get_scope("fake_scoped", "w1")["scope"] == {"m2": "*"}
    assert "dormant" not in result.output.lower()


def test_scope_clear_last_entry_warns_dormant(in_proc_daemon):
    _register("fake_scoped", "w1")
    _put_scope("fake_scoped", "w1", {"m1": "*"})
    result = _runner.invoke(cli_app, ["scope", "clear", "fake_scoped:w1", "--machine", "m1"])
    assert result.exit_code == 0, result.output
    assert _get_scope("fake_scoped", "w1")["scope"] == {}
    assert "dormant" in result.output.lower()


def test_scope_clear_all_restores_active_everywhere(in_proc_daemon):
    _register("fake_scoped", "w1")
    _put_scope("fake_scoped", "w1", {"m1": "*"})
    result = _runner.invoke(cli_app, ["scope", "clear", "fake_scoped:w1"])
    assert result.exit_code == 0, result.output
    assert _get_scope("fake_scoped", "w1")["scope"] is None
    lowered = result.output.lower()
    assert "everywhere" in lowered or "every machine" in lowered


def test_scope_clear_bad_ref_exit_2(in_proc_daemon):
    result = _runner.invoke(cli_app, ["scope", "clear", "noref"])
    assert result.exit_code == 2
