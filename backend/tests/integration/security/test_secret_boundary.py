"""The secret boundary against a real in-process daemon (spec credentials,
mcp-gateway, vault-sync).

Only a present human sees a secret's plaintext or sends it somewhere new. The
desktop app's half — the presence check and the signed grant — is played by
``BoundaryDaemon.grant``, which signs exactly as the shell does.
"""

from __future__ import annotations

import base64
import json
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest
from typer.testing import CliRunner

from coffer.domain.credential_errors import SecretBindingPending
from coffer.surfaces.cli import _approvals
from coffer.surfaces.cli.main import app as cli_app
from tests.support.boundary_daemon import (
    BoundaryDaemon,
    point_cli_at,
    prepare_home,
    running_daemon,
)

_runner = CliRunner()


def _master_key() -> str:
    from coffer.surfaces.http.credential_composition import get_master_key_manager

    return (get_master_key_manager().current or b"").decode()


@pytest.fixture
def daemon(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[BoundaryDaemon]:
    db = prepare_home(tmp_path, monkeypatch)
    with running_daemon(tmp_path, db) as d:
        yield d


@pytest.fixture
def cli(daemon: BoundaryDaemon, monkeypatch: pytest.MonkeyPatch) -> BoundaryDaemon:
    point_cli_at(daemon, monkeypatch)
    return daemon


def _two_servers(d: BoundaryDaemon) -> tuple[dict[str, Any], dict[str, Any]]:
    d.store("gh/token", "ghp_boundary_value_1")
    first = d.register_stdio("first", "server-one", {"TOKEN": "gh/token"})
    assert d.resolve_for(first) == {"TOKEN": "ghp_boundary_value_1"}
    second = d.register_stdio("second", "evil.sh", {"TOKEN": "gh/token"})
    return first, second


# --- no plaintext out -----------------------------------------------------------


@pytest.mark.acceptance(spec="credentials", scenario="no route or command hands out a stored value")
def test_no_route_or_command_hands_out_a_stored_value(cli: BoundaryDaemon) -> None:
    d = cli
    d.store("gh/token", "ghp_never_printed_42")

    read = d.client.get("/api/v1/credentials/gh/token")
    export = d.client.post("/api/v1/sync/key/export", json={})
    shown = _runner.invoke(cli_app, ["credentials", "get", "gh/token", "--show"])
    exported = _runner.invoke(cli_app, ["sync", "key", "export", str(d.home / "k")])

    assert read.status_code in (404, 405)
    assert export.status_code in (404, 405)
    assert shown.exit_code == 2 and exported.exit_code == 2
    key = _master_key()
    for body in (read.text, export.text, shown.output, exported.output):
        assert "ghp_never_printed_42" not in body and key not in body
    assert not (d.home / "k").exists()


@pytest.mark.acceptance(
    spec="credentials", scenario="a reveal with a valid grant returns the value once"
)
def test_a_reveal_with_a_valid_grant_returns_the_value_once(daemon: BoundaryDaemon) -> None:
    d = daemon
    d.store("gh/token", "ghp_reveal_me_42")
    grant = d.grant("reveal", "gh/token")

    r = d.client.post("/api/v1/credentials/presence/reveal", json={"ref": "gh/token", **grant})
    again = d.client.post("/api/v1/credentials/presence/reveal", json={"ref": "gh/token", **grant})

    assert r.status_code == 200 and r.json() == {"value": "ghp_reveal_me_42"}
    assert again.status_code == 403
    assert again.json()["error"]["code"] == "PRESENCE_GRANT_INVALID"
    entries = d.audit("credential_revealed")
    assert len(entries) == 1 and "gh/token" in json.dumps(entries[0]["details"])
    assert "ghp_reveal_me_42" not in json.dumps(entries)


@pytest.mark.acceptance(
    spec="credentials", scenario="a grant for one operation authorises nothing else"
)
def test_a_grant_for_one_operation_authorises_nothing_else(daemon: BoundaryDaemon) -> None:
    d = daemon
    d.store("gh/token", "ghp_one")
    d.store("other/token", "ghp_two")

    forged = d.grant("reveal", "gh/token")
    forged["signature"] = "0" * 64
    wrong_ref = d.grant("reveal", "gh/token")
    wrong_op = d.grant("reveal", "gh/token")

    r1 = d.client.post("/api/v1/credentials/presence/reveal", json={"ref": "gh/token", **forged})
    r2 = d.client.post(
        "/api/v1/credentials/presence/reveal", json={"ref": "other/token", **wrong_ref}
    )
    d.register_stdio("a", "one", {"T": "other/token"})
    b = d.register_stdio("b", "two", {"T": "other/token"})
    [waiting] = d.pending(destination_uid=b["uid"])
    r3 = d.client.post(f"/api/v1/credentials/approvals/{waiting['id']}/approve", json=wrong_op)

    for r in (r1, r2, r3):
        assert r.status_code == 403 and r.json()["error"]["code"] == "PRESENCE_GRANT_INVALID"
        assert "ghp_" not in r.text
    assert d.pending(destination_uid=b["uid"])[0]["id"] == waiting["id"]


@pytest.mark.acceptance(
    spec="credentials", scenario="the master key backup is written only against a grant"
)
def test_the_master_key_backup_is_written_only_against_a_grant(
    daemon: BoundaryDaemon, tmp_path: pathlib.Path
) -> None:
    d = daemon
    target = tmp_path / "picked"
    target.mkdir()
    refused = d.client.post(
        "/api/v1/credentials/presence/master-key-export",
        json={"directory": str(target), "nonce": "x" * 16, "signature": "0" * 64},
    )
    assert refused.status_code == 403 and list(target.iterdir()) == []

    r = d.client.post(
        "/api/v1/credentials/presence/master-key-export",
        json={"directory": str(target), **d.grant("export_master_key", str(target))},
    )

    assert r.status_code == 200, r.text
    written = pathlib.Path(r.json()["path"])
    assert written.parent == target and (written.stat().st_mode & 0o777) == 0o600
    key = _master_key()
    assert written.read_text().strip() == key and key not in r.text
    assert len(d.audit("master_key_exported")) == 1


# --- new destinations -------------------------------------------------------------


@pytest.mark.acceptance(
    spec="credentials",
    scenario="citing an existing secret from a new MCP server waits for approval",
)
def test_citing_an_existing_secret_from_a_new_server_waits(daemon: BoundaryDaemon) -> None:
    d = daemon
    first, second = _two_servers(d)

    with pytest.raises(SecretBindingPending) as refused:
        d.resolve_for(second)

    [waiting] = d.pending(destination_uid=second["uid"])
    assert waiting["ref"] == "gh/token" and waiting["target"] == "stdio evil.sh"
    assert refused.value.approval_ids == [waiting["id"]]
    assert d.resolve_for(first) == {"TOKEN": "ghp_boundary_value_1"}


@pytest.mark.acceptance(
    spec="mcp-gateway", scenario="a server whose secret is not approved is not spawned with it"
)
def test_the_test_route_spawns_nothing_until_approved(
    daemon: BoundaryDaemon, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coffer.infrastructure.mcp import probe as server_probe

    spawned: list[dict[str, str]] = []

    class _Conn:
        def __init__(self, *, env_overlay: dict[str, str], **_: Any) -> None:
            spawned.append(env_overlay)

        async def spawn_and_initialize(self) -> dict[str, Any]:
            return {}

        async def request(self, method: str, params: dict[str, Any]) -> Any:
            return type("Listed", (), {"tools": []})()

        async def close(self) -> None:
            return None

    monkeypatch.setattr(server_probe, "StdioUpstreamConnection", _Conn)
    # The fake command is not on PATH; the probe's pre-spawn check is not under test.
    monkeypatch.setattr(server_probe, "_launcher_problem", lambda *_a: None)
    d = daemon
    _first, second = _two_servers(d)

    held = d.client.post(f"/api/v1/resources/mcp_server/{second['uid']}/test").json()
    assert held["ok"] is False and "waiting for approval in the Coffer app" in held["error_message"]
    assert spawned == []

    d.approve(d.pending(destination_uid=second["uid"])[0]["id"])
    after = d.client.post(f"/api/v1/resources/mcp_server/{second['uid']}/test").json()
    assert after["ok"], (after["error_code"], after["error_message"])
    assert spawned == [{"TOKEN": "ghp_boundary_value_1"}]


@pytest.mark.acceptance(spec="credentials", scenario="changing where a secret goes asks again")
def test_changing_where_a_secret_goes_asks_again(daemon: BoundaryDaemon) -> None:
    d = daemon
    first, _second = _two_servers(d)
    config = {**first["config"]}
    config["transport"] = {**config["transport"], "command": "curl-to-attacker"}
    r = d.client.patch(f"/api/v1/resources/{first['uid']}", json={"config": config})
    assert r.status_code == 200, r.text
    moved = r.json()

    with pytest.raises(SecretBindingPending):
        d.resolve_for(moved)
    [waiting] = d.pending(destination_uid=first["uid"])
    assert waiting["target"] == "stdio curl-to-attacker"

    d.approve(waiting["id"])
    assert d.resolve_for(moved) == {"TOKEN": "ghp_boundary_value_1"}
    assert len(d.audit("secret_approval_approved")) == 1


@pytest.mark.acceptance(
    spec="credentials", scenario="a value supplied for its destination needs no approval"
)
def test_a_value_supplied_for_a_new_server_needs_no_approval(daemon: BoundaryDaemon) -> None:
    d = daemon
    d.store("mcp_server/fresh/TOKEN", "fresh-value-123")
    server = d.register_stdio("fresh", "server", {"TOKEN": "mcp_server/fresh/TOKEN"})
    assert d.pending() == []
    assert d.resolve_for(server) == {"TOKEN": "fresh-value-123"}


@pytest.mark.acceptance(
    spec="mcp-gateway",
    scenario="a stdio server with a secret is marked readable by local processes",
)
def test_a_stdio_server_with_a_secret_is_marked(daemon: BoundaryDaemon) -> None:
    d = daemon
    d.store("t/one", "value-one-123")
    d.register_stdio("with-secret", "server", {"T": "t/one"})
    d.register_stdio("without", "server", {})
    http = {
        "transport": {
            "type": "http",
            "url": "https://mcp.example.com/",
            "credential_refs": {"Authorization": "t/one"},
        }
    }
    assert (
        d.client.post(
            "/api/v1/resources", json={"kind": "mcp_server", "name": "remote", "config": http}
        ).status_code
        == 201
    )

    rows = d.client.get("/api/v1/resources", params={"kind": "mcp_server"}).json()["resources"]
    flags = {r["name"]: r["secrets_readable_by_local_processes"] for r in rows}
    assert flags == {"with-secret": True, "without": False, "remote": False}


# --- the command line --------------------------------------------------------------


@pytest.mark.acceptance(
    spec="credentials", scenario="the command line reports a pending approval and exits 9"
)
def test_the_command_line_reports_a_pending_approval_and_exits_9(cli: BoundaryDaemon) -> None:
    d = cli
    d.store("gh/token", "ghp_cli_value_1")
    d.register_stdio("first", "server-one", {"TOKEN": "gh/token"})
    d.pending()

    added = _runner.invoke(
        cli_app, ["mcp", "add", "second", "--stdio", "evil.sh", "--credential", "TOKEN=gh/token"]
    )

    assert added.exit_code == 9, added.output
    assert "registered: mcp_server second" in added.output
    assert "waiting for approval in the Coffer app" in added.output
    listed = _runner.invoke(cli_app, ["credentials", "approvals", "--json"])
    assert listed.exit_code == 0
    [row] = json.loads(listed.output)["approvals"]
    assert row["destination_label"] == "second" and row["id"] in added.output


@pytest.mark.acceptance(
    spec="credentials", scenario="the command line waits for the approval with --wait"
)
def test_the_command_line_waits_for_the_approval(
    cli: BoundaryDaemon, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = cli
    d.store("gh/token", "ghp_cli_value_2")
    d.register_stdio("first", "server-one", {"TOKEN": "gh/token"})
    d.pending()

    def the_person_approves(_seconds: float) -> None:
        for approval in d.pending():
            d.approve(approval["id"])

    monkeypatch.setattr(_approvals.time, "sleep", the_person_approves)
    added = _runner.invoke(
        cli_app,
        ["mcp", "add", "second", "--stdio", "b.sh", "--credential", "TOKEN=gh/token", "--wait"],
    )

    assert added.exit_code == 0, added.output
    assert "approved in the Coffer app" in added.output


def test_rejecting_needs_no_presence(cli: BoundaryDaemon) -> None:
    d = cli
    _first, second = _two_servers(d)
    [waiting] = d.pending(destination_uid=second["uid"])
    r = _runner.invoke(cli_app, ["credentials", "reject", waiting["id"]])
    assert r.exit_code == 0, r.output
    # Refused stays refused for this target: not asked again, still withheld.
    assert d.pending() == []
    with pytest.raises(SecretBindingPending):
        d.resolve_for(second)
    assert len(d.audit("secret_approval_rejected")) == 1


@pytest.mark.acceptance(spec="credentials", scenario="replacing a value in use waits for approval")
def test_replacing_a_value_in_use_waits(daemon: BoundaryDaemon) -> None:
    d = daemon
    _two_servers(d)

    r = d.client.post(
        "/api/v1/credentials", json={"ref": "gh/token", "value": "attacker-bot-token"}
    )

    assert r.status_code == 202, r.text
    approval = r.json()["approval"]
    assert approval["op"] == "replace_value" and "attacker-bot-token" not in r.text
    assert d.value("gh/token") == "ghp_boundary_value_1"
    [held] = d.local_secrets("approvals")["approvals"]
    assert held["pending_ciphertext"]
    assert b"attacker-bot-token" not in base64.b64decode(held["pending_ciphertext"])
    d.approve(approval["id"])
    assert d.value("gh/token") == "attacker-bot-token"
    assert [a["pending_ciphertext"] for a in d.local_secrets("approvals")["approvals"]] == [None]


@pytest.mark.acceptance(
    spec="credentials", scenario="switching the protection off waits for the desktop app"
)
def test_switching_the_protection_off_waits(cli: BoundaryDaemon) -> None:
    d = cli
    off = _runner.invoke(cli_app, ["config", "set", "secrets.require_approval", "off"])
    assert off.exit_code == 9, off.output
    assert "waiting for approval in the Coffer app" in off.output
    status = d.client.get("/api/v1/settings/secret-boundary").json()
    assert status["require_approval"] is True

    d.approve(status["pending_approval_id"])
    assert d.client.get("/api/v1/settings/secret-boundary").json()["require_approval"] is False
    _first, second = _two_servers(d)
    assert d.resolve_for(second) == {"TOKEN": "ghp_boundary_value_1"}

    on = _runner.invoke(cli_app, ["config", "set", "secrets.require_approval", "on"])
    assert on.exit_code == 0, on.output


# --- the listing ---------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="credentials", scenario="a secret nothing references is listed as unreferenced"
)
def test_a_secret_nothing_references_is_listed_as_unreferenced(daemon: BoundaryDaemon) -> None:
    d = daemon
    skill = d.home / ".coffer" / "vault" / "skills" / "db-tools"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("Run with coffer://secret/used-one set.\n")
    d.store("secret/lonely", "lonely-value-1")
    d.store("secret/used-one", "used-value-12")

    rows = {r["ref"]: r for r in d.client.get("/api/v1/credentials").json()["refs"]}

    assert rows["secret/lonely"]["unreferenced"] is True
    assert rows["secret/lonely"]["readable_by_local_processes"] is True
    assert rows["secret/lonely"]["uri"] == "coffer://secret/lonely"
    assert rows["secret/used-one"]["mentioned_by_skills"] == ["db-tools"]
    assert rows["secret/used-one"]["unreferenced"] is False
    refused = d.client.delete("/api/v1/credentials/secret/used-one")
    assert refused.status_code == 409
    assert "skill 'db-tools'" in refused.json()["error"]["details"]["references"]
    assert d.value("secret/used-one") == "used-value-12"


# --- the sync remote --------------------------------------------------------------------


@pytest.mark.acceptance(
    spec="vault-sync", scenario="a push token pointed at a new URL waits for approval"
)
def test_a_push_token_pointed_at_a_new_url_waits(daemon: BoundaryDaemon) -> None:
    from coffer.domain.secrets import sync_remote_destination
    from coffer.surfaces.http.credential_composition import get_credential_store
    from coffer.surfaces.http.secret_boundary_wiring import boundary_resolver

    d = daemon
    d.store("sync/push-token", "push-token-value")
    resolver = boundary_resolver(get_credential_store())
    first = sync_remote_destination("https://git.example.com/me/vault.git")
    assert resolver.materialize({"token": "sync/push-token"}, first) == {
        "token": "push-token-value"
    }

    moved = sync_remote_destination("https://attacker.example.net/vault.git")
    with pytest.raises(SecretBindingPending) as refused:
        resolver.materialize({"token": "sync/push-token"}, moved)

    [approval_id] = refused.value.approval_ids
    assert d.boundary.get(approval_id).target == "git https://attacker.example.net/vault.git"
    d.boundary.approve(approval_id, actor="desktop")
    assert resolver.materialize({"token": "sync/push-token"}, moved) == {
        "token": "push-token-value"
    }


# --- provider connections -----------------------------------------------------------------


@pytest.mark.acceptance(
    spec="credentials", scenario="moving a provider connection's base URL asks again"
)
def test_moving_a_provider_base_url_asks_again(daemon: BoundaryDaemon) -> None:
    import asyncio

    from coffer.domain.provider.config import ProviderConfig
    from coffer.surfaces.http.provider_dependencies import get_provider_service

    d = daemon
    r = d.client.post(
        "/api/v1/providers",
        json={
            "name": "gw",
            "protocol": "anthropic",
            "base_url": "https://gw.example.com/anthropic",
            "secret_value": "sk-provider-key-1",
        },
    )
    assert r.status_code == 201, r.text
    uid = r.json()["uid"]
    svc = get_provider_service()

    def key_now() -> str:
        row = d.client.get(f"/api/v1/resources/{uid}").json()
        cfg = ProviderConfig.model_validate(row["config"])
        return asyncio.run(svc._key_of(cfg, label="gw", uid=uid))

    assert key_now() == "sk-provider-key-1"

    moved = d.client.patch(
        f"/api/v1/providers/{uid}", json={"base_url": "https://attacker.example.net/v1"}
    )
    assert moved.status_code == 200, moved.text
    with pytest.raises(SecretBindingPending):
        key_now()
    [waiting] = d.pending(destination_uid=uid)
    assert waiting["target"] == "model api https://attacker.example.net/v1"
    d.approve(waiting["id"])
    assert key_now() == "sk-provider-key-1"

    ref = d.client.get(f"/api/v1/providers/{uid}").json()["credential_ref"]
    rotated = d.client.patch(f"/api/v1/providers/{uid}", json={"secret_value": "sk-replaced-2"})
    assert rotated.status_code == 200, rotated.text
    assert d.value(ref) == "sk-provider-key-1"
    [replace] = [a for a in d.pending() if a["op"] == "replace_value"]
    d.approve(replace["id"])
    assert d.value(ref) == "sk-replaced-2" and key_now() == "sk-replaced-2"


def _provider(d: BoundaryDaemon, name: str, base_url: str, **body: Any) -> dict[str, Any]:
    r = d.client.post(
        "/api/v1/providers",
        json={"name": name, "protocol": "anthropic", "base_url": base_url, **body},
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


@pytest.mark.acceptance(
    spec="credentials", scenario="the command line reports a pending provider key and exits 9"
)
def test_the_command_line_reports_a_pending_provider_key(cli: BoundaryDaemon) -> None:
    d = cli
    gw = _provider(d, "gw", "https://gw.example.com/anthropic", secret_value="sk-cli-key-1")
    d.pending()  # the first key, just typed for this connection, is approved on sight
    ref = d.client.get(f"/api/v1/providers/{gw['uid']}").json()["credential_ref"]

    rotated = _runner.invoke(cli_app, ["provider", "edit", "gw", "--secret", "sk-cli-key-2"])
    assert rotated.exit_code == 9, rotated.output
    assert "updated provider gw" in rotated.output
    assert "waiting for approval in the Coffer app" in rotated.output
    [replace] = [a for a in d.pending() if a["op"] == "replace_value"]
    assert replace["id"] in rotated.output and d.value(ref) == "sk-cli-key-1"

    moved = _runner.invoke(
        cli_app, ["provider", "edit", "gw", "--base-url", "https://elsewhere.example.net/v1"]
    )
    assert moved.exit_code == 9, moved.output
    [bind] = d.pending(destination_uid=gw["uid"])
    assert bind["id"] in moved.output and "waiting for approval" in moved.output

    added = _runner.invoke(
        cli_app,
        [
            "provider",
            "add",
            "second",
            "--protocol",
            "anthropic",
            "--base-url",
            "https://second.example.org/v1",
            "--credential-ref",
            ref,
        ],
    )
    assert added.exit_code == 9, added.output
    assert "added provider second" in added.output
    assert "waiting for approval in the Coffer app" in added.output

    described = _runner.invoke(cli_app, ["provider", "edit", "gw", "--description", "gateway"])
    assert described.exit_code == 0, described.output


def test_provider_edit_waits_for_the_approval_with_wait(
    cli: BoundaryDaemon, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = cli
    _provider(d, "gw", "https://gw.example.com/anthropic", secret_value="sk-wait-key-1")
    d.pending()

    def the_person_approves(_seconds: float) -> None:
        for approval in d.pending():
            d.approve(approval["id"])

    monkeypatch.setattr(_approvals.time, "sleep", the_person_approves)
    r = _runner.invoke(cli_app, ["provider", "edit", "gw", "--secret", "sk-wait-key-2", "--wait"])
    assert r.exit_code == 0, r.output
    assert "approved in the Coffer app" in r.output
