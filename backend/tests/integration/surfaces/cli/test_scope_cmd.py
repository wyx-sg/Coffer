"""Integration tests for `coffer scope ...` CLI subcommands (ADR per-agent-resource-scope).

Reuses the shared ``in_proc_daemon`` fixture (see conftest.py), which wires
``fake_scoped`` (supports_scope=True, mirrors the four kinds that carry reach —
mcp_server, skill, provider, channel) alongside the plain ``fake_kind`` (no
scope support, mirrors agent, knowledge and memory) used by
test_resource_cmd.py. Doubles rather than real kinds on purpose: what is under
test is the ``coffer scope`` surface, which must behave identically for any
kind, so a kind withdrawing from reach — as knowledge and memory did — changes
nothing here.

Setup/assertions talk to the resource-scope HTTP routes directly via the
monkeypatched client (bypassing the CLI, like test_resource_cmd.py's
``_register`` helper) so each test only exercises the CLI surface under
test through ``coffer scope ...`` itself.

**Two vocabularies meet in this module and the tests say which is which.** The
stored allow-list holds agent UIDS; the command line speaks agent NAMES (ADR
resource-identity-is-an-immutable-uid). So a test that sets a scope asserts
UIDS were written, and a test that shows one asserts NAMES came back — that
round trip is the behaviour ``scope_cmd`` exists to provide, and asserting only
one end of it would let the translation drop out unnoticed.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict
from typer.testing import CliRunner

from coffer.domain.resource import Kind
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http.dependencies import get_resource_service

_runner = CliRunner()


class _AgentDoubleConfig(BaseModel):
    """Lenient config for the ``agent`` double below — nothing here cares what
    an agent is configured with, only that one exists to be resolved."""

    model_config = ConfigDict(extra="allow")


def _register(kind: str, name: str) -> str:
    """Register a resource over HTTP and return the uid creation minted."""
    client, _info = _cli_client.client_or_exit()
    r = client.post("/resources", json={"kind": kind, "name": name, "config": {}})
    assert r.status_code == 201, r.text
    return str(r.json()["uid"])


def _agent(name: str) -> str:
    """An agent row called ``name``, returning its uid.

    ``scope set --agents`` takes the names a person typed and writes the uids
    they resolve to, and ``scope show`` renders those uids back as names — so
    this module needs real agent rows to resolve against. It needed none while
    the allow-list held names: the CLI wrote whatever was typed, which is
    exactly the "two spellings of one agent" this change removed.

    The ``agent`` kind is a double registered on the running service rather
    than a widening of the shared fixture: ``coffer scope`` is the only CLI
    surface that resolves agent names against an in-process daemon, and what is
    under test is that resolution, not what an agent actually is.
    """
    client, _info = _cli_client.client_or_exit()
    svc = client.app.dependency_overrides[get_resource_service]()
    # The fixture builds a fresh kinds map per test, so this neither leaks into
    # another test nor collides with a second call inside one.
    svc._kinds.setdefault(
        "agent",
        Kind(name="agent", display_name="Agent", config_schema=_AgentDoubleConfig),
    )
    return _register("agent", name)


def _get_scope(uid: str) -> dict:
    client, _info = _cli_client.client_or_exit()
    r = client.get(f"/resources/{uid}/scope")
    assert r.status_code == 200, r.text
    return r.json()


def _put_scope(uid: str, scope: object) -> None:
    """Write a scope over HTTP. The wire shape is the one-axis object
    (``{"agents": [...]}``) or ``null`` — never a bare list. The agents in it
    are UIDS: this is the stored value, not the command line."""
    client, _info = _cli_client.client_or_exit()
    r = client.put(f"/resources/{uid}/scope", json={"scope": scope})
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# scope show
# ---------------------------------------------------------------------------


def test_scope_show_happy_path(in_proc_daemon):
    _register("fake_scoped", "w1")
    result = _runner.invoke(cli_app, ["scope", "show", "fake_scoped", "w1"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["scope"] is None
    assert body["supports_scope"] is True


def test_scope_show_reports_kinds_without_scope(in_proc_daemon):
    client, _info = _cli_client.client_or_exit()
    r = client.post("/resources", json={"kind": "fake_kind", "name": "n1", "config": {"foo": 1}})
    assert r.status_code == 201, r.text
    result = _runner.invoke(cli_app, ["scope", "show", "fake_kind", "n1"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["scope"] is None
    assert body["supports_scope"] is False


def test_scope_show_reflects_current_scope(in_proc_daemon):
    """What is stored is uids; what is shown is names."""
    uid = _register("fake_scoped", "w1")
    cc, codex = _agent("claude-code"), _agent("codex")
    _put_scope(uid, {"agents": [cc, codex]})
    result = _runner.invoke(cli_app, ["scope", "show", "fake_scoped", "w1"])
    assert result.exit_code == 0, result.output
    # The same two agents the scope was written with, in the same order, named
    # the way the person who set it named them. Printing the stored uids would
    # be literally true and useless.
    assert json.loads(result.output)["scope"] == {
        "agents": ["claude-code", "codex"],
    }


def test_scope_show_without_a_name_exits_2(in_proc_daemon):
    """Both arguments are required, and a missing one is a usage error.

    This stood for "a ``<kind>:<name>`` ref that does not parse exits 2" while
    the ref was a string a user had to spell correctly. There is no such string
    any more — kind and name are two arguments — so what carries the same
    meaning is the argument list itself being short: the command refuses
    without touching the daemon rather than guessing at what was meant.
    """
    result = _runner.invoke(cli_app, ["scope", "show", "fake_scoped"])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# scope set
# ---------------------------------------------------------------------------


def test_scope_set_with_agents(in_proc_daemon):
    uid = _register("fake_scoped", "w1")
    cc, codex = _agent("claude-code"), _agent("codex")
    result = _runner.invoke(
        cli_app, ["scope", "set", "fake_scoped", "w1", "--agents", "claude-code,codex"]
    )
    assert result.exit_code == 0, result.output
    # Names went in; the uids they resolve to are what was written. The stored
    # value is what a rename has to survive, so it is what is asserted here.
    assert _get_scope(uid)["scope"] == {"agents": [cc, codex]}


def test_scope_set_refuses_an_agent_name_that_resolves_to_nothing(in_proc_daemon):
    """A typo'd name is refused, not passed through.

    A uid nothing matches is a legal stored value — a machine may be scoped to
    an agent it does not have yet — so nothing downstream would complain. That
    is precisely why the refusal belongs here: written through, a typo would
    produce a scope that quietly matches one agent fewer than the user thinks,
    and "never silently widen" cuts the other way too.
    """
    uid = _register("fake_scoped", "w1")
    _agent("claude-code")
    result = _runner.invoke(
        cli_app, ["scope", "set", "fake_scoped", "w1", "--agents", "claude-code,ghost"]
    )
    assert result.exit_code == 4
    assert _get_scope(uid)["scope"] is None  # nothing was written at all


def test_scope_set_replaces_the_whole_list(in_proc_daemon):
    uid = _register("fake_scoped", "w1")
    cc, codex = _agent("claude-code"), _agent("codex")
    cursor = _agent("cursor")
    _put_scope(uid, {"agents": [cc, codex]})
    result = _runner.invoke(cli_app, ["scope", "set", "fake_scoped", "w1", "--agents", "cursor"])
    assert result.exit_code == 0, result.output
    assert _get_scope(uid)["scope"] == {"agents": [cursor]}


def test_scope_set_no_agents_is_dormant(in_proc_daemon):
    uid = _register("fake_scoped", "w1")
    result = _runner.invoke(cli_app, ["scope", "set", "fake_scoped", "w1", "--no-agents"])
    assert result.exit_code == 0, result.output
    assert _get_scope(uid)["scope"] == {"agents": []}
    assert "dormant" in result.output.lower()


def test_scope_set_requires_exactly_one_mode(in_proc_daemon):
    _register("fake_scoped", "w1")
    neither = _runner.invoke(cli_app, ["scope", "set", "fake_scoped", "w1"])
    assert neither.exit_code == 2

    both = _runner.invoke(
        cli_app, ["scope", "set", "fake_scoped", "w1", "--agents", "codex", "--no-agents"]
    )
    assert both.exit_code == 2


def test_scope_set_empty_agents_list_exit_2(in_proc_daemon):
    """`--agents ","` (no actual names) must not silently PUT a dormant scope."""
    uid = _register("fake_scoped", "w1")
    result = _runner.invoke(cli_app, ["scope", "set", "fake_scoped", "w1", "--agents", ","])
    assert result.exit_code == 2
    assert _get_scope(uid)["scope"] is None


def test_scope_set_on_kind_without_scope_fails(in_proc_daemon):
    client, _info = _cli_client.client_or_exit()
    r = client.post("/resources", json={"kind": "fake_kind", "name": "n2", "config": {"foo": 1}})
    assert r.status_code == 201, r.text
    # The agent exists, so the refusal can only come from the kind — without it
    # the command would fail one step earlier, on a name nothing matches, and
    # this test would pass while proving nothing about scopeless kinds.
    _agent("codex")
    result = _runner.invoke(cli_app, ["scope", "set", "fake_kind", "n2", "--agents", "codex"])
    assert result.exit_code != 0


def test_scope_set_without_a_name_exits_2(in_proc_daemon):
    """As above: a short argument list is refused before the daemon is asked."""
    result = _runner.invoke(cli_app, ["scope", "set", "fake_scoped", "--agents", "codex"])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# scope clear
# ---------------------------------------------------------------------------


def test_scope_clear_restores_active_for_every_agent(in_proc_daemon):
    uid = _register("fake_scoped", "w1")
    _put_scope(uid, {"agents": [_agent("claude-code")]})
    result = _runner.invoke(cli_app, ["scope", "clear", "fake_scoped", "w1"])
    assert result.exit_code == 0, result.output
    assert _get_scope(uid)["scope"] is None
    assert "every agent" in result.output.lower()


def test_scope_clear_from_dormant(in_proc_daemon):
    uid = _register("fake_scoped", "w1")
    _put_scope(uid, {"agents": []})
    result = _runner.invoke(cli_app, ["scope", "clear", "fake_scoped", "w1"])
    assert result.exit_code == 0, result.output
    assert _get_scope(uid)["scope"] is None


def test_scope_clear_without_a_name_exits_2(in_proc_daemon):
    """As above: a short argument list is refused before the daemon is asked."""
    result = _runner.invoke(cli_app, ["scope", "clear", "fake_scoped"])
    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# The label is not the identity
# ---------------------------------------------------------------------------


def test_a_renamed_resource_keeps_the_scope_it_was_given(in_proc_daemon):
    """The point of the whole change, from this surface's side.

    The scope is stored against the resource's uid, so relabelling the resource
    cannot move, drop or orphan it — and ``scope show`` finds it again under
    the new name. While the name WAS the identity this could not even be asked.
    """
    uid = _register("fake_scoped", "w1")
    cc = _agent("claude-code")
    assert (
        _runner.invoke(
            cli_app, ["scope", "set", "fake_scoped", "w1", "--agents", "claude-code"]
        ).exit_code
        == 0
    )

    client, _info = _cli_client.client_or_exit()
    r = client.patch(f"/resources/{uid}", json={"name": "w2"})
    assert r.status_code == 200, r.text

    assert _get_scope(uid)["scope"] == {"agents": [cc]}
    shown = _runner.invoke(cli_app, ["scope", "show", "fake_scoped", "w2"])
    assert shown.exit_code == 0, shown.output
    assert json.loads(shown.output)["scope"] == {"agents": ["claude-code"]}
