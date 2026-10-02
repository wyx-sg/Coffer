"""`coffer provider …` CLI coverage (spec provider-switching).

Wires a minimal provider-only in-process daemon and monkeypatches
``client_or_exit`` to a Starlette TestClient over it (mirrors the conftest's
``in_proc_daemon`` pattern).

The daemon registers two ``agent`` rows as well, which it did not need to
before: a connection's reach is a scope holding agent UIDS
(ADR identity-is-the-uid-inside-the-file), so both the CLI resolving the name
a user typed and ``scoped_targets`` resolving the stored uid back into an agent
TYPE need the registry to actually contain them.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from typer.testing import CliRunner

from coffer.application.agent.kind import make_agent_kind
from coffer.application.audit_service import AuditService
from coffer.application.provider.kind import make_provider_kind
from coffer.application.provider.proxy_tokens import ProxyTokenService
from coffer.application.provider.service import ProviderService
from coffer.application.resource_service import ResourceService
from coffer.domain.model_proxy.state import ProxyState
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.provider_dependencies import get_provider_service
from coffer.surfaces.http.provider_routes import router as provider_router
from coffer.surfaces.http.proxy_dependencies import ProxyFacade, set_proxy_facade
from coffer.surfaces.http.proxy_routes import router as proxy_router
from coffer.surfaces.http.resource_routes import router as resource_router
from tests.support.facets import agent_catalog
from tests.support.no_approvals import router as no_approvals_router
from tests.support.vault_stores import make_resource_repo

_runner = CliRunner()
_TOKEN = "test-token-011-cli"


class _DictStore:
    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        return self._d.get(ref)

    def set(self, ref: str, value: str) -> None:
        self._d[ref] = value

    def delete(self, ref: str) -> None:
        self._d.pop(ref, None)


class _RegisteredAgents:
    """The agent registry ``ProviderService`` resolves a scope against.

    A scope names agents by uid, and a uid says nothing about the agent's type
    on its own — only the registry knows which product a uid is. So this reads
    the rows rather than returning the empty list it used to: with no rows, a
    scoped connection would report reaching nothing, which is the right answer
    for an empty registry and the wrong one for these tests.
    """

    def __init__(self, resources: ResourceService) -> None:
        self._resources = resources

    async def list(self):
        return await self._resources.list(kind="agent")

    async def set_connection(self, uid, connection_uid, *, actor="api"):
        """What the agent kind does for a switch: write the field on the record."""
        row = await self._resources.get(uid)
        return await self._resources.update_config(
            uid,
            {**row.config, "connection_uid": connection_uid},
            actor,
            allow_lifecycle_kind=True,
        )


async def _create_tables(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture
def provider_daemon(tmp_path, monkeypatch):
    engine = create_async_engine_with_pragmas(f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    loop = asyncio.new_event_loop()
    loop.run_until_complete(_create_tables(engine))
    loop.close()
    sm = session_maker(engine)
    store = _DictStore()
    audit = AuditService(SqlAlchemyAuditRepo(sm))
    resources = ResourceService(
        kinds={"provider": make_provider_kind(), "agent": make_agent_kind()},
        repo=make_resource_repo(),
        audit=audit,
        secrets=store,
    )
    # One agent of each type, registered through the service because the agent
    # kind refuses the generic create path. They exist so `coffer provider
    # scope <name> --agents <agent-name>` has a name to resolve to a uid.
    loop = asyncio.new_event_loop()
    for agent_name, agent_type in (("claude-code", "claude_code"), ("codex", "codex")):
        loop.run_until_complete(
            resources.register(
                kind="agent",
                name=agent_name,
                config={"type": agent_type, "config_dir": str(tmp_path / agent_name)},
                actor="test",
                allow_lifecycle_kind=True,
            )
        )
    loop.close()
    provider_svc = ProviderService(
        agent_catalog=agent_catalog(),
        resources=resources,
        secrets=store,
        config_store=ConfigFileStore(),
        agents=_RegisteredAgents(resources),
        audit=audit,
    )

    app = FastAPI()
    err_handlers.register(app)
    app.include_router(provider_router)
    # The connection's reach is a scope edit now (ADR per-agent-resource-scope), and that
    # goes through the framework's shared resource route, so the CLI test app
    # must serve it too.
    app.include_router(resource_router)
    app.include_router(no_approvals_router)
    app.include_router(proxy_router)
    tokens = ProxyTokenService(store)

    async def _noop() -> None:
        return None

    async def _agent_exists(agent_uid: str) -> bool:
        return any(a.uid == agent_uid for a in await resources.list(kind="agent"))

    async def _state() -> ProxyState:
        return ProxyState()

    set_proxy_facade(
        ProxyFacade(
            tokens=tokens,
            status=lambda: {},
            refresh=_noop,
            agent_exists=_agent_exists,
            state=_state,
        )
    )
    app.dependency_overrides[get_provider_service] = lambda: provider_svc
    # One override serves two readers: the CLI resolves the name a user typed
    # through ``/resources``, and the provider routes read the agent rows a
    # connection's scope names by uid off the same kind-agnostic service.
    app.dependency_overrides[get_resource_service] = lambda: resources
    set_active_token(_TOKEN)

    fake_client = TestClient(
        app,
        base_url="http://localhost/api/v1",
        headers={"X-Coffer-Token": _TOKEN},
        raise_server_exceptions=False,
    )
    monkeypatch.setattr(_cli_client, "client_or_exit", lambda: (fake_client, object()))
    yield audit
    set_active_token(None)
    set_proxy_facade(None)


def _add(name: str = "acme", *extra: str, protocol: str = "anthropic") -> None:
    r = _runner.invoke(
        cli_app,
        [
            "provider",
            "add",
            name,
            "--protocol",
            protocol,
            "--base-url",
            f"https://gw/{protocol}",
            "--secret",
            "sk-x",
            *extra,
        ],
    )
    assert r.exit_code == 0, r.output


def _agent_connection(agent_name: str) -> str | None:
    """The connection uid the named agent's record carries."""
    c, _info = _cli_client.client_or_exit()
    r = c.get("/resources", params={"kind": "agent", "name": agent_name})
    assert r.status_code == 200, r.text
    [row] = r.json()["resources"]
    return row["config"].get("connection_uid")


def _show(name: str) -> dict:
    r = _runner.invoke(cli_app, ["provider", "show", name, "--json"])
    assert r.exit_code == 0, r.output
    return json.loads(r.output)


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="the command line covers create, list, switch and revert",
)
def test_cli_create_list_switch(provider_daemon):
    r = _runner.invoke(
        cli_app,
        [
            "provider",
            "add",
            "acme",
            "--protocol",
            "anthropic",
            "--base-url",
            "https://gw/anthropic",
            "--secret",
            "sk-x",
        ],
    )
    assert r.exit_code == 0, r.output
    assert "added provider acme" in r.output

    r = _runner.invoke(cli_app, ["provider", "list", "--json"])
    assert r.exit_code == 0, r.output
    [row] = json.loads(r.output)["resources"]
    assert row["name"] == "acme" and row["config"]["protocol"] == "anthropic"

    table = _runner.invoke(cli_app, ["provider", "list"], env={"COLUMNS": "200"})
    assert table.exit_code == 0, table.output
    assert "acme" in table.output and "https://gw/anthropic" in table.output

    # Without --agent every registered agent the connection reaches is switched.
    r = _runner.invoke(cli_app, ["provider", "switch", "acme"])
    assert r.exit_code == 0, r.output
    assert "switched claude-code to acme" in r.output
    uid = _show("acme")["uid"]
    assert _agent_connection("claude-code") == uid
    assert _agent_connection("codex") == uid

    # `--agent` switches one agent and leaves the other where it is.
    _add("other")
    r = _runner.invoke(cli_app, ["provider", "switch", "other", "--agent", "codex"])
    assert r.exit_code == 0, r.output
    assert _agent_connection("codex") == _show("other")["uid"]
    assert _agent_connection("claude-code") == uid


def test_cli_add_takes_a_title_and_description(provider_daemon):
    _add("acme", "--title", "Acme gateway", "--description", "the EU one")
    shown = _show("acme")
    assert shown["title"] == "Acme gateway"
    assert shown["description"] == "the EU one"


def test_cli_scope_retargets_a_connection(provider_daemon):
    # An openai gateway re-targeted at Claude Code: which agents a connection
    # reaches is the framework's per-agent scope (ADR per-agent-resource-scope),
    # set with the group's own `scope` verb.
    _add("agnes", protocol="openai")

    # The wire's own default is what a new connection starts on: unscoped.
    reach = _runner.invoke(cli_app, ["provider", "scope", "agnes", "--json"])
    assert reach.exit_code == 0, reach.output
    assert json.loads(reach.output)["scope"] is None

    # `--agents` takes agent NAMES, resolved to the uids the stored scope holds.
    narrowed = _runner.invoke(cli_app, ["provider", "scope", "agnes", "--agents", "claude-code"])
    assert narrowed.exit_code == 0, narrowed.output
    assert "claude-code" in narrowed.output
    reach = _runner.invoke(cli_app, ["provider", "scope", "agnes", "--json"])
    assert json.loads(reach.output)["scope"] == {"agents": ["claude-code"]}


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="the command line covers create, list, switch and revert",
)
@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="switch an agent back to its built-in login",
)
def test_cli_builtin_reverts_an_agent_to_its_own_login(provider_daemon):
    """`switch`'s other half: a terminal-only user can take an agent off a
    Coffer connection again."""
    _add("acme")
    assert _runner.invoke(cli_app, ["provider", "switch", "acme"]).exit_code == 0

    reverted = _runner.invoke(cli_app, ["provider", "builtin", "claude_code"])
    assert reverted.exit_code == 0, reverted.output
    assert "acme" in reverted.output

    # The agent no longer names a connection — and only that agent changed.
    assert _agent_connection("claude-code") is None
    assert _agent_connection("codex") == _show("acme")["uid"]

    # Idempotent: the agent is on its own login now, and a second revert still succeeds.
    again = _runner.invoke(cli_app, ["provider", "builtin", "claude_code"])
    assert again.exit_code == 0, again.output
    assert "no connection" in again.output


def test_cli_builtin_rejects_what_is_not_an_agent_type(provider_daemon):
    """A wire or an unknown name is a usage error the user can read, not a
    traceback."""
    for bad_arg in ("smoke-signals", "anthropic"):
        bad = _runner.invoke(cli_app, ["provider", "builtin", bad_arg])
        combined = bad.output + (bad.stderr or "")
        assert bad.exit_code == 6, combined
        assert "not an agent type" in combined, combined
    bad = _runner.invoke(cli_app, ["provider", "builtin", "smoke-signals"])
    combined = bad.output + (bad.stderr or "")
    assert bad.exit_code == 6, combined
    assert "Traceback" not in combined, combined


def test_cli_removed_provider_commands_are_gone(provider_daemon):
    """The defaults are `coffer config` keys and the revert is `builtin` now."""
    for gone in ("use-builtin", "internal-default", "transcribe-default", "rename", "key"):
        r = _runner.invoke(cli_app, ["provider", gone, "--help"])
        assert r.exit_code != 0, gone
        assert "No such command" in r.output


def test_cli_edit_corrects_a_mis_probed_wire(provider_daemon):
    """The probe that guessed the wire can be wrong, so `edit --protocol`
    corrects it in place — the key does not have to be re-entered."""
    _add("agnes")
    ref = _show("agnes")["config"]["secret_ref"]

    edited = _runner.invoke(cli_app, ["provider", "edit", "agnes", "--protocol", "openai"])
    assert edited.exit_code == 0, edited.output

    shown = _show("agnes")
    assert shown["config"]["protocol"] == "openai"
    assert shown["config"]["secret_ref"] == ref


def test_cli_edit_rotates_the_key_in_place(provider_daemon):
    _add("acme")
    before = _show("acme")
    rotated = _runner.invoke(cli_app, ["provider", "edit", "acme", "--secret", "sk-new"])
    assert rotated.exit_code == 0, rotated.output
    after = _show("acme")
    assert after["config"]["secret_ref"] == before["config"]["secret_ref"]


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="correcting a mis-probed wire is refused while the connection is live",
)
def test_cli_edit_refuses_to_move_the_wire_while_the_connection_is_live(provider_daemon):
    """The daemon refuses; the CLI reports the conflict with an exit code of its
    own and the message naming `coffer provider builtin <agent_type>` as the way out."""
    _add("acme")
    assert _runner.invoke(cli_app, ["provider", "switch", "acme"]).exit_code == 0

    refused = _runner.invoke(
        cli_app, ["provider", "edit", "acme", "--protocol", "openai", "--name", "acme-eu"]
    )
    combined = refused.output + (refused.stderr or "")
    assert refused.exit_code == 5, combined
    assert "Traceback" not in combined, combined
    assert "coffer provider builtin claude_code" in combined, combined
    shown = _show("acme")
    # A refused wire change renames nothing either.
    assert shown["name"] == "acme"
    assert shown["config"]["protocol"] == "anthropic"

    # The way out works: revert every agent running on it, edit, and the wire moves.
    assert "coffer provider builtin codex" in combined, combined
    assert _runner.invoke(cli_app, ["provider", "builtin", "claude_code"]).exit_code == 0
    assert _runner.invoke(cli_app, ["provider", "builtin", "codex"]).exit_code == 0
    ok = _runner.invoke(cli_app, ["provider", "edit", "acme", "--protocol", "openai"])
    assert ok.exit_code == 0, ok.output
    assert _show("acme")["config"]["protocol"] == "openai"


def test_cli_edit_with_no_options_is_a_usage_error(provider_daemon):
    """`edit` with nothing to change says so rather than sending an empty patch."""
    empty = _runner.invoke(cli_app, ["provider", "edit", "acme"])
    assert empty.exit_code == 6, empty.output + (empty.stderr or "")


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="rename a connection from the command line",
)
def test_cli_edit_name_renames_the_same_connection(provider_daemon):
    """`coffer provider edit acme --name acme-eu` is a label change: same uid,
    same stored key, a `resource_renamed` entry naming both names; a name
    another connection holds is refused with the route's error."""
    audit = provider_daemon
    _add("acme")
    _add("taken")
    before = _show("acme")

    renamed = _runner.invoke(cli_app, ["provider", "edit", "acme", "--name", "acme-eu"])
    assert renamed.exit_code == 0, renamed.output
    assert "acme-eu" in renamed.output

    after = _show("acme-eu")
    assert after["uid"] == before["uid"]
    assert after["config"]["secret_ref"] == before["config"]["secret_ref"]

    entries = asyncio.run(audit.query(event_type="resource_renamed"))
    assert [(e.details["from"], e.details["to"]) for e in entries] == [("acme", "acme-eu")]

    clash = _runner.invoke(cli_app, ["provider", "edit", "acme-eu", "--name", "taken"])
    combined = clash.output + (clash.stderr or "")
    assert clash.exit_code == 5, combined
    assert "RESOURCE_ALREADY_EXISTS" in combined or "already" in combined, combined
    assert "Traceback" not in combined, combined
    assert _show("acme-eu")["uid"] == before["uid"]


def test_cli_edit_title_leaves_the_name_alone(provider_daemon):
    _add("acme")
    r = _runner.invoke(cli_app, ["provider", "edit", "acme", "--title", "Acme EU"])
    assert r.exit_code == 0, r.output
    shown = _show("acme")
    assert shown["name"] == "acme" and shown["title"] == "Acme EU"


def test_cli_edit_of_a_missing_connection_is_not_found(provider_daemon):
    """The name is resolved to a uid before anything is sent, so a name nobody
    holds is reported here rather than as a 404 on a uid the user never saw."""
    missing = _runner.invoke(cli_app, ["provider", "edit", "ghost", "--name", "spectre"])
    combined = missing.output + (missing.stderr or "")
    assert missing.exit_code == 4, combined
    assert "ghost" in combined, combined


def test_cli_rm_removes_the_connection(provider_daemon):
    _add("acme")
    r = _runner.invoke(cli_app, ["provider", "rm", "acme", "--yes"])
    assert r.exit_code == 0, r.output
    listed = _runner.invoke(cli_app, ["provider", "list", "--json"])
    assert json.loads(listed.output)["resources"] == []


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="the token command prints a local token, never a provider key",
)
def test_cli_proxy_token_prints_a_local_token(provider_daemon):
    added = _runner.invoke(
        cli_app,
        [
            "provider",
            "add",
            "acme",
            "--protocol",
            "anthropic",
            "--base-url",
            "https://gw/anthropic",
            "--secret",
            "sk-never-printed",
        ],
    )
    assert added.exit_code == 0, added.output
    assert _runner.invoke(cli_app, ["provider", "switch", "acme"]).exit_code == 0
    client, _ = _cli_client.client_or_exit()
    rows = client.get("/resources", params={"kind": "agent", "name": "claude-code"}).json()
    agent = rows["resources"][0]

    r = _runner.invoke(cli_app, ["proxy", "token", "--agent-uid", agent["uid"]])
    assert r.exit_code == 0, r.output
    token = r.output.strip()
    assert token.startswith("cfr_") and len(token) > 40
    assert "sk-never-printed" not in r.output
    # The same token every time, until it is rotated.
    again = _runner.invoke(cli_app, ["proxy", "token", "--agent-uid", agent["uid"]])
    assert again.output.strip() == token

    missing = _runner.invoke(cli_app, ["proxy", "token", "--agent-uid", "0" * 32])
    assert missing.exit_code == 4
    assert missing.stdout == ""
