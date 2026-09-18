"""`coffer provider …` CLI coverage (spec provider-switching).

Wires a minimal provider-only in-process daemon and monkeypatches
``client_or_exit`` to a Starlette TestClient over it (mirrors the conftest's
``in_proc_daemon`` pattern).

The daemon registers two ``agent`` rows as well, which it did not need to
before: a connection's reach is a scope holding agent UIDS
(ADR resource-identity-is-an-immutable-uid), so both the CLI resolving the name
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
from coffer.application.provider.service import ProviderService
from coffer.application.resource_service import ResourceService
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.infrastructure.persistence.base import Base
from coffer.infrastructure.persistence.engine import (
    create_async_engine_with_pragmas,
    session_maker,
)
from coffer.infrastructure.persistence.repos import SqlAlchemyAuditRepo, SqlAlchemyResourceRepo
from coffer.surfaces.cli import _client as _cli_client
from coffer.surfaces.cli.main import app as cli_app
from coffer.surfaces.http import errors as err_handlers
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.dependencies import get_resource_service
from coffer.surfaces.http.provider_dependencies import get_provider_service
from coffer.surfaces.http.provider_routes import router as provider_router
from coffer.surfaces.http.resource_routes import router as resource_router

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
        repo=SqlAlchemyResourceRepo(sm),
        audit=audit,
        credentials=store,
    )
    # One agent of each type, registered through the service because the agent
    # kind refuses the generic create path. They exist so `coffer scope set
    # provider <name> --agents <agent-name>` has a name to resolve to a uid.
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
        resources=resources,
        credentials=store,
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
    yield
    set_active_token(None)


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
    assert [p["name"] for p in json.loads(r.output)["providers"]] == ["acme"]

    r = _runner.invoke(cli_app, ["provider", "switch", "acme"])
    assert r.exit_code == 0, r.output
    assert "switched to acme" in r.output


def test_cli_key_by_connection_and_scope(provider_daemon):
    # An openai gateway re-targeted at Claude Code. `--compatible` is gone:
    # which agents a connection reaches is the framework's per-agent scope
    # (ADR per-agent-resource-scope), set through the shared `coffer scope` surface.
    r = _runner.invoke(
        cli_app,
        [
            "provider",
            "add",
            "agnes",
            "--protocol",
            "openai",
            "--base-url",
            "https://agnes/v1",
            "--secret",
            "sk-agnes",
        ],
    )
    assert r.exit_code == 0, r.output

    # The wire's own default is what a new connection starts on.
    show = _runner.invoke(cli_app, ["provider", "show", "agnes"])
    assert json.loads(show.output)["compatible_agents"] == ["claude_code", "codex"]

    # `--agents` takes agent NAMES; `coffer scope` resolves each to the uid the
    # stored scope holds. `claude-code` is the agent's name, `claude_code` is
    # its TYPE — and the type is what `compatible_agents` reports back, because
    # a projection writes the agent PRODUCT's file.
    narrowed = _runner.invoke(
        cli_app, ["scope", "set", "provider", "agnes", "--agents", "claude-code"]
    )
    assert narrowed.exit_code == 0, narrowed.output
    show = _runner.invoke(cli_app, ["provider", "show", "agnes"])
    assert json.loads(show.output)["compatible_agents"] == ["claude_code"]

    # --connection-uid prints exactly that connection's key. It takes the UID,
    # not a name, because its caller is the `apiKeyHelper` line Coffer wrote
    # into the agent's own config file: that line has to keep resolving to this
    # connection after the user relabels it
    # (ADR resource-identity-is-an-immutable-uid).
    uid = json.loads(_runner.invoke(cli_app, ["provider", "show", "agnes"]).output)["uid"]
    key = _runner.invoke(cli_app, ["provider", "key", "--connection-uid", uid])
    assert key.exit_code == 0, key.output
    assert key.output.strip() == "sk-agnes"

    # No selector → usage error.
    assert _runner.invoke(cli_app, ["provider", "key"]).exit_code == 6


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="the command line covers create, list, switch and revert",
)
def test_cli_use_builtin_reverts_a_wire_to_the_agents_own_login(provider_daemon):
    """`switch`'s other half. POST /providers/use-builtin/{wire} has backed the
    Model providers page since the deactivate path landed; the CLI had
    activate's half and not this one, so a terminal-only user could put an
    agent onto a Coffer connection and never take it off again."""
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
            "sk-x",
        ],
    )
    assert added.exit_code == 0, added.output
    assert _runner.invoke(cli_app, ["provider", "switch", "acme"]).exit_code == 0

    reverted = _runner.invoke(cli_app, ["provider", "use-builtin", "anthropic"])
    assert reverted.exit_code == 0, reverted.output
    assert "acme" in reverted.output

    # The connection is no longer active for its wire.
    shown = _runner.invoke(cli_app, ["provider", "show", "acme"])
    assert json.loads(shown.output)["is_active"] is False


def test_cli_use_builtin_is_idempotent_when_nothing_is_active(provider_daemon):
    """The route is a no-op when the agent already runs built-in, and the CLI
    must report that rather than fail."""
    reverted = _runner.invoke(cli_app, ["provider", "use-builtin", "anthropic"])
    assert reverted.exit_code == 0, reverted.output


def test_cli_use_builtin_rejects_a_wire_that_is_not_one(provider_daemon):
    """An unknown wire is a usage error the user can read, not a traceback."""
    bad = _runner.invoke(cli_app, ["provider", "use-builtin", "smoke-signals"])
    combined = bad.output + (bad.stderr or "")
    assert bad.exit_code == 6, combined
    assert "Traceback" not in combined, combined


def test_cli_edit_corrects_a_mis_probed_wire(provider_daemon):
    """`PATCH /providers/{name}` has accepted `protocol` since the probe could
    be wrong; the CLI could not send it, and its help said the field was
    immutable — so a terminal-only user had no way to correct a wrong wire at
    all, and was told the correction did not exist."""
    added = _runner.invoke(
        cli_app,
        [
            "provider",
            "add",
            "agnes",
            "--protocol",
            "anthropic",
            "--base-url",
            "https://agnes/v1",
            "--secret",
            "sk-agnes",
        ],
    )
    assert added.exit_code == 0, added.output
    ref = json.loads(_runner.invoke(cli_app, ["provider", "show", "agnes"]).output)[
        "credential_ref"
    ]

    edited = _runner.invoke(cli_app, ["provider", "edit", "agnes", "--protocol", "openai"])
    assert edited.exit_code == 0, edited.output

    shown = json.loads(_runner.invoke(cli_app, ["provider", "show", "agnes"]).output)
    assert shown["protocol"] == "openai"
    # Corrected in place: the key did not have to be re-entered, which is the
    # whole reason the field is mutable.
    assert shown["credential_ref"] == ref


def test_cli_edit_refuses_to_move_the_wire_while_the_connection_is_live(provider_daemon):
    """The wire is not inert: it decides whether a connection can cover any
    agent at all (an ollama one covers none) and which wire `use-builtin`
    reverts. Moving it under a live projection would strand the native config
    already written, so the daemon refuses and the CLI reports the conflict
    with an exit code of its own, not a traceback."""
    _runner.invoke(
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
    assert _runner.invoke(cli_app, ["provider", "switch", "acme"]).exit_code == 0

    refused = _runner.invoke(cli_app, ["provider", "edit", "acme", "--protocol", "openai"])
    combined = refused.output + (refused.stderr or "")
    assert refused.exit_code == 5, combined
    assert "Traceback" not in combined, combined
    # The message has to name the way out, or the user is simply stuck.
    assert "use-builtin" in combined, combined
    assert (
        json.loads(_runner.invoke(cli_app, ["provider", "show", "acme"]).output)["protocol"]
        == "anthropic"
    )

    # The way out works: revert, edit, and the wire moves.
    assert _runner.invoke(cli_app, ["provider", "use-builtin", "anthropic"]).exit_code == 0
    ok = _runner.invoke(cli_app, ["provider", "edit", "acme", "--protocol", "openai"])
    assert ok.exit_code == 0, ok.output
    assert (
        json.loads(_runner.invoke(cli_app, ["provider", "show", "acme"]).output)["protocol"]
        == "openai"
    )


def test_cli_edit_with_no_options_is_a_usage_error(provider_daemon):
    """`edit` with nothing to change must say so rather than send an empty
    patch — the guard added `--protocol` to that list, so it is re-pinned."""
    empty = _runner.invoke(cli_app, ["provider", "edit", "acme"])
    assert empty.exit_code == 6, empty.output + (empty.stderr or "")


def test_cli_rename_is_the_kind_agnostic_verb_now(provider_daemon):
    """`coffer provider rename` is GONE, and nothing was lost with it.

    It existed because the connection's NAME was written out into another
    tool's config file, so moving the name had to move that projection too.
    The projected `apiKeyHelper` cites the uid now
    (ADR resource-identity-is-an-immutable-uid), which leaves a rename as what
    it always was for the other kinds: a label change. So it is served by the
    kind-agnostic verb, and this test asserts the thing that actually matters —
    that the connection is the SAME connection afterwards.
    """
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
            "sk-x",
        ],
    )
    assert added.exit_code == 0, added.output
    before = json.loads(_runner.invoke(cli_app, ["provider", "show", "acme"]).output)

    renamed = _runner.invoke(cli_app, ["resource", "rename", "provider", "acme", "acme-eu"])
    assert renamed.exit_code == 0, renamed.output
    assert "acme-eu" in renamed.output

    assert [
        p["name"]
        for p in json.loads(_runner.invoke(cli_app, ["provider", "list", "--json"]).output)[
            "providers"
        ]
    ] == ["acme-eu"]

    after = json.loads(_runner.invoke(cli_app, ["provider", "show", "acme-eu"]).output)
    # The identity did not move, so neither did anything hung off it: the key
    # stayed at the address the connection owns, and the helper Coffer already
    # projected still names a connection that exists.
    assert after["uid"] == before["uid"]
    assert after["credential_ref"] == before["credential_ref"]
    key = _runner.invoke(cli_app, ["provider", "key", "--connection-uid", after["uid"]])
    assert key.exit_code == 0, key.output
    assert key.output.strip() == "sk-x"


def test_cli_rename_reports_a_name_already_taken(provider_daemon):
    """A name is still unique within its kind — a user should not end up with
    two connections called the same thing — so a collision is a 409, which the
    CLI must surface as a readable message and the conflict exit code rather
    than a traceback."""
    for name in ("acme", "beta"):
        _runner.invoke(
            cli_app,
            [
                "provider",
                "add",
                name,
                "--protocol",
                "anthropic",
                "--base-url",
                "https://gw/anthropic",
                "--secret",
                "sk-x",
            ],
        )

    clash = _runner.invoke(cli_app, ["resource", "rename", "provider", "acme", "beta"])
    combined = clash.output + (clash.stderr or "")
    assert clash.exit_code == 5, combined
    assert "Traceback" not in combined, combined


def test_cli_rename_of_a_missing_connection_is_not_found(provider_daemon):
    """The name is resolved to a uid before anything is sent, so a name nobody
    holds is reported here rather than as a 404 on a uid the user never saw."""
    missing = _runner.invoke(cli_app, ["resource", "rename", "provider", "ghost", "spectre"])
    combined = missing.output + (missing.stderr or "")
    assert missing.exit_code == 4, combined
    assert "ghost" in combined, combined
