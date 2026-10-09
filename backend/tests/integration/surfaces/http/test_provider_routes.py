"""End-to-end HTTP coverage for /api/v1/providers/* (spec provider-switching).

Every route under this prefix addresses a connection by its immutable ``uid``
(ADR identity-is-the-uid-inside-the-file). The ``name`` beside it is a label:
these tests assert on it, and resolve *through* it only via the one route that
still finds a resource by label (``_uids_named`` below).
"""

from __future__ import annotations

import json
import pathlib
import re
import tomllib

import pytest
from starlette.testclient import TestClient

from coffer.domain.model_proxy.state import ProxyState
from coffer.domain.provider.projection import is_managed_api_key_helper
from coffer.infrastructure.agent.config_file_store import ConfigFileStore
from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token
from coffer.surfaces.http.proxy_dependencies import get_proxy_facade


def _assert_proxy_form(settings: dict) -> None:
    """Claude Code is pointed at the local model proxy and fetches its own
    local token: neither the connection's endpoint nor its key is in the file."""
    helper = settings["apiKeyHelper"]
    assert is_managed_api_key_helper(helper), helper
    assert " proxy token --agent-uid " in helper, helper
    assert settings["env"]["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:38471/anthropic"


def _proxy_state(c: TestClient) -> ProxyState:
    """What the supervisor would push the proxy right now."""
    return c.portal.call(get_proxy_facade().state)  # type: ignore[union-attr]


def _route_keys(c: TestClient) -> dict[str, tuple[str, str | None]]:
    """``agent_uid -> (connection_uid, key)`` for every route in the state."""
    return {r.agent_uid: (r.member.connection_uid, r.member.key) for r in _proxy_state(c).routes}


TOKEN = "test-token-011"


def _new(c, body: dict) -> str:
    """Create a connection and hand back its ``uid``.

    Taken straight off the creation response, the earliest place the identity
    is available; everything downstream is addressed with it, never the label.
    """
    r = c.post("/api/v1/providers", json=body)
    assert r.status_code == 201, r.text
    return r.json()["uid"]


def _uids_named(c, name: str) -> list[str]:
    """Every provider uid currently carrying the label ``name``.

    ``GET /api/v1/resources?kind=<kind>&name=<label>`` is the ONE route left
    that finds a resource by name — the door a surface starting from something
    a human typed (the CLI) uses to reach a uid. A LIST rather than one uid,
    because that is what lets a rename test say the old label now resolves to
    nothing, which is a different claim from "the new one resolves".
    """
    r = c.get("/api/v1/resources", params={"kind": "provider", "name": name})
    assert r.status_code == 200, r.text
    return [row["uid"] for row in r.json()["resources"]]


def _ref_of(c, uid: str) -> str:
    """The vault address a connection's config names.

    Read rather than spelled out: the ref is an ADDRESS the config holds, and
    deriving it from the connection's name is exactly what made the name a key.
    """
    return c.get(f"/api/v1/providers/{uid}").json()["secret_ref"]


def _key_present(c, ref: str) -> bool:
    return c.get(f"/api/v1/secrets/{ref}/exists").json()["present"] is True


def _app(tmp_path: pathlib.Path, monkeypatch, port_start: int):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("COFFER_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'c.db'}")
    monkeypatch.setenv("COFFER_PORT_RANGE_START", str(port_start))
    monkeypatch.setenv("COFFER_PORT_RANGE_END", str(port_start + 9))
    return create_app()


def _client(app) -> TestClient:
    set_active_token(TOKEN)
    return TestClient(app, headers={"X-Coffer-Token": TOKEN})


def _agent_dir(tmp_path: pathlib.Path, name: str = "agent-cfg") -> pathlib.Path:
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _register_agent(c: TestClient, *, agent_type: str, config_dir: pathlib.Path) -> str:
    """Register the one agent of ``agent_type`` (named by the type) and return
    its uid — what a resource scope now holds.

    A scope's ``agents`` list names agent UIDS, not type values: a provider
    scope used to hold type values while other kinds' scopes held names, and
    the uid is the one vocabulary every kind's scope now speaks.
    """
    r = c.post(
        "/api/v1/agents",
        json={"type": agent_type, "config_dir": str(config_dir)},
    )
    assert r.status_code == 201, r.text
    return r.json()["uid"]


def _activate(c: TestClient, uid: str, agent_type: str = "claude_code"):
    """Switch the agent of ``agent_type`` onto connection ``uid``."""
    return c.post(f"/api/v1/providers/{uid}/activate", json={"agent_type": agent_type})


def _connection_of(c: TestClient, agent_type: str) -> str | None:
    """The uid of the connection the agent of ``agent_type`` runs on."""
    return c.get(f"/api/v1/agents/{agent_type}").json()["connection_uid"]


def _anthropic_body(name: str = "acme", **over) -> dict:
    body = {
        "name": name,
        "protocol": "anthropic",
        "base_url": "https://gw/anthropic",
        "secret_value": "sk-secret-value",
    }
    body.update(over)
    return body


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="create an anthropic provider profile with an inline secret",
)
def test_create_with_inline_secret(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59710)
    with _client(app) as c:
        r = c.post("/api/v1/providers", json=_anthropic_body())
        assert r.status_code == 201, r.text
        body = r.json()
        # The identity is minted here and is the value every other route takes.
        # It is a uuid4 hex — business-agnostic on purpose, so nothing the user
        # can edit (the label above all) can be read back out of it, and so two
        # machines converging this vault agree on which resource is which.
        assert len(body["uid"]) == 32 and int(body["uid"], 16) >= 0
        assert body["uid"] != body["name"] and body["name"] == "acme"
        # The minted ref is opaque — the connection's name must not be
        # recoverable from it, or the name is a key again.
        ref = body["secret_ref"]
        assert re.fullmatch(r"secret/[0-9a-f]{32}", ref) and "acme" not in ref
        # the secret landed in the vault under that ref
        ex = c.get(f"/api/v1/secrets/{ref}/exists")
        assert ex.status_code == 200 and ex.json()["present"] is True
        # ...but never in the API response
        assert "sk-secret-value" not in r.text


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="create a profile that reuses an existing secret ref",
)
def test_create_reusing_secret_ref(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59720)
    with _client(app) as c:
        c.post("/api/v1/secrets", json={"ref": "secret/" + "d" * 32, "value": "sk-shared"})
        r = c.post(
            "/api/v1/providers",
            json={
                "name": "reuse",
                "protocol": "openai",
                "base_url": "https://gw/v1",
                "secret_ref": "secret/" + "d" * 32,
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["secret_ref"] == "secret/" + "d" * 32


@pytest.mark.acceptance(
    spec="provider-switching", scenario="reject a profile with an unknown wire format"
)
def test_reject_unknown_wire_format(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59730)
    with _client(app) as c:
        r = c.post("/api/v1/providers", json=_anthropic_body(protocol="bogus"))
        assert r.status_code == 422, r.text


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="reject a profile that supplies neither a secret nor a secret ref",
)
def test_reject_no_secret_source(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59740)
    body = _anthropic_body()
    body.pop("secret_value")
    with _client(app) as c:
        r = c.post("/api/v1/providers", json=body)
        assert r.status_code == 422, r.text
        assert "PROVIDER_SECRET_SOURCE_INVALID" in r.text


@pytest.mark.acceptance(spec="provider-switching", scenario="update a provider profile")
def test_update_profile(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59750)
    with _client(app) as c:
        uid = _new(c, _anthropic_body())
        r = c.patch(f"/api/v1/providers/{uid}", json={"base_url": "https://gw/anthropic/v2"})
        assert r.status_code == 200, r.text
        assert r.json()["base_url"] == "https://gw/anthropic/v2"


def test_patch_can_correct_the_wire(tmp_path, monkeypatch):
    """The wire is a property of the endpoint, not the connection's identity.

    A probe that guessed wrong is corrected in place rather than by deleting the
    connection and re-entering its key. ``secret_ref`` stays immutable: that
    one IS an address.

    This connection was never switched on, which is the only state the edit is
    free in — a live one is refused (``test_protocol_edit_guard``), because the
    wire decides whether a connection can cover any agent at all.
    """
    app = _app(tmp_path, monkeypatch, 59755)
    with _client(app) as c:
        uid = _new(c, _anthropic_body())
        r = c.patch(f"/api/v1/providers/{uid}", json={"protocol": "openai"})
        assert r.status_code == 200, r.text
        assert r.json()["protocol"] == "openai"

        # The retired ollama protocol is not a wire a connection can move onto.
        bad = c.patch(f"/api/v1/providers/{uid}", json={"protocol": "ollama"})
        assert bad.status_code == 422, bad.text
        assert bad.json()["error"]["code"] == "PROVIDER_PROTOCOL_RETIRED"


def _store_retired_flag(tmp_path: pathlib.Path) -> pathlib.Path:
    """A hand edit of the one connection file, settled the way the scanner would:
    its config carries the retired ``internal_default`` flag."""
    from coffer.infrastructure.vault.instance import vault_writer

    [path] = (tmp_path / ".coffer" / "vault" / "resources" / "provider").glob("*.json")
    doc = json.loads(path.read_text())
    doc["config"]["internal_default"] = True
    path.write_text(json.dumps(doc, indent=2) + "\n")
    vault_writer().settle([f"resources/provider/{path.name}"])
    return path


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="ignore a stored internal-default flag when a connection is read",
)
def test_a_stored_internal_default_flag_is_ignored_on_read(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59762)
    with _client(app) as c:
        uid = _new(c, _anthropic_body())
        _store_retired_flag(tmp_path)

        r = c.get("/api/v1/providers")
        assert r.status_code == 200, r.text
        [row] = r.json()["providers"]
        assert row["uid"] == uid and row["base_url"] == "https://gw/anthropic"
        assert "internal_default" not in row


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="drop a stored internal-default flag on the next write",
)
def test_a_stored_internal_default_flag_is_dropped_on_the_next_write(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59764)
    with _client(app) as c:
        uid = _new(c, _anthropic_body())
        path = _store_retired_flag(tmp_path)
        assert "internal_default" in json.loads(path.read_text())["config"]

        r = c.patch(f"/api/v1/providers/{uid}", json={"base_url": "https://gw/anthropic/v3"})
        assert r.status_code == 200, r.text

        config = json.loads(path.read_text())["config"]
        assert "internal_default" not in config
        assert config["base_url"] == "https://gw/anthropic/v3"


@pytest.mark.acceptance(spec="provider-switching", scenario="list provider profiles")
def test_list_profiles(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59760)
    with _client(app) as c:
        a = _new(c, _anthropic_body(name="a"))
        b = _new(c, _anthropic_body(name="b"))
        r = c.get("/api/v1/providers")
        assert r.status_code == 200
        rows = r.json()["providers"]
        assert {p["name"] for p in rows} == {"a", "b"}
        # Every row carries its identity beside its label, so a client that
        # listed can address any of them without a second lookup.
        assert {p["uid"] for p in rows} == {a, b}


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="delete a provider profile cleans up its owned secret",
)
def test_delete_cleans_owned_secret(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59770)
    with _client(app) as c:
        uid = _new(c, _anthropic_body())
        ref = _ref_of(c, uid)
        assert _key_present(c, ref)
        r = c.delete(f"/api/v1/providers/{uid}")
        assert r.status_code == 204, r.text
        assert not _key_present(c, ref)


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="activate an anthropic profile writes Claude Code settings",
)
def test_activate_writes_claude_settings(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59780)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", config_dir=cfg)
        uid = _new(c, _anthropic_body())
        r = _activate(c, uid)
        assert r.status_code == 200, r.text
        assert r.json()["agent"] == "claude-code"
        # The connection is recorded on the AGENT, not as a flag on itself.
        assert _connection_of(c, "claude_code") == uid
        data = json.loads((cfg / "settings.json").read_text())
        # Claude Code calls the local proxy with its own token; the
        # connection's endpoint and key stay with the proxy, so this file
        # never names the connection and a rename rewrites nothing.
        _assert_proxy_form(data)
        assert "gw/anthropic" not in json.dumps(data)
        # The agent is unbound (no per-agent model) → no model env is written, so
        # Claude Code runs on its OWN default model (spec provider-switching
        # "Take projected model keys from the agent's binding").
        assert "ANTHROPIC_MODEL" not in data["env"]
        assert "ANTHROPIC_SMALL_FAST_MODEL" not in data["env"]


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="an agent's model binding drives the projected model",
)
def test_agent_binding_drives_projected_model(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59783)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        cc = _register_agent(c, agent_type="claude_code", config_dir=cfg)
        uid = _new(c, _anthropic_body())
        # Bind this agent to its own models; activating projects them (the model
        # lives on the binding, not the connection — spec provider-switching
        # "Take projected model keys from the agent's binding").
        rb = c.patch(
            f"/api/v1/agents/{cc}",
            json={
                "model": "bound-opus",
                "tier_models": {"haiku": "bound-haiku", "opus": "bound-opus"},
            },
        )
        assert rb.status_code == 200, rb.text
        assert rb.json()["model"] == "bound-opus"
        _activate(c, uid)
        data = json.loads((cfg / "settings.json").read_text())
        assert data["model"] == "bound-opus"
        assert "effortLevel" not in data
        assert data["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "bound-haiku"
        assert data["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "bound-opus"
        assert "ANTHROPIC_MODEL" not in data["env"]
        assert "ANTHROPIC_SMALL_FAST_MODEL" not in data["env"]


@pytest.mark.acceptance(
    spec="provider-switching", scenario="activate an openai profile writes Codex config"
)
def test_activate_writes_codex_config(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59790)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        cx = _register_agent(c, agent_type="codex", config_dir=cfg)
        uid = _new(
            c,
            {
                "name": "oa",
                "protocol": "openai",
                "base_url": "https://gw/v1",
                "secret_value": "sk-x",
            },
        )
        # Bind the agent's model so the projection writes a top-level model (the
        # model lives on the binding, not the connection — spec provider-switching
        # "Take projected model keys from the agent's binding").
        c.patch(f"/api/v1/agents/{cx}", json={"model": "gpt-x"})
        r = _activate(c, uid, "codex")
        assert r.status_code == 200, r.text
        assert r.json()["agent"] == "codex"
        assert _connection_of(c, "codex") == uid
        doc = tomllib.loads((cfg / "config.toml").read_text())
        assert doc["model"] == "gpt-x"
        assert doc["model_provider"] == "coffer"
        block = doc["model_providers"]["coffer"]
        # Codex calls the local proxy and fetches its own local token; the
        # upstream and its key stay with the proxy.
        assert block["base_url"] == "http://127.0.0.1:38471/openai/v1"
        assert block["wire_api"] == "responses"
        assert block["supports_websockets"] is False
        assert block["requires_openai_auth"] is False
        assert block["auth"]["args"] == ["proxy", "token", "--agent-uid", cx]
        assert "env_key" not in block
        assert "sk-x" not in (cfg / "config.toml").read_text()


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="switch an agent back to its built-in login",
)
def test_use_builtin_removes_projection_and_clears_active(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59785)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", config_dir=cfg)
        uid = _new(c, _anthropic_body())
        _activate(c, uid)
        assert _connection_of(c, "claude_code") == uid
        # sanity — the connection is projected into the agent config first
        assert json.loads((cfg / "settings.json").read_text())["env"]["ANTHROPIC_BASE_URL"]

        # ``use-builtin`` is addressed by AGENT type, not by a connection or a
        # wire: it is the agent that is being put back on its own login, and
        # which connection was covering it is what the route answers rather
        # than what it takes.
        r = c.post("/api/v1/providers/use-builtin/claude_code")
        assert r.status_code == 200, r.text
        assert r.json()["agent_type"] == "claude_code"
        assert r.json()["deprojected"] == ["claude-code"]
        # ``previous`` is a LABEL — it is there for a human reading the result,
        # not for addressing anything.
        assert r.json()["previous"] == "acme"

        # projection removed → the agent falls back to its own built-in login
        data = json.loads((cfg / "settings.json").read_text())
        assert "apiKeyHelper" not in data
        assert "ANTHROPIC_BASE_URL" not in data.get("env", {})
        # and the agent no longer names a connection
        assert _connection_of(c, "claude_code") is None


def test_use_builtin_is_idempotent_noop(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59786)
    with _client(app) as c:
        # Nothing active for the agent type → use-builtin is a clean no-op.
        r = c.post("/api/v1/providers/use-builtin/codex")
        assert r.status_code == 200, r.text
        assert r.json()["deprojected"] == []
        assert r.json()["previous"] is None


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a wire no longer names an agent to revert",
)
def test_use_builtin_takes_an_agent_type_not_a_wire(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59787)
    with _client(app) as c:
        assert c.post("/api/v1/providers/use-builtin/anthropic").status_code == 422
        assert c.post("/api/v1/providers/use-builtin/gemini_cli").status_code == 422


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="switching one agent onto a connection moves only that agent",
)
def test_switching_one_agent_moves_only_that_agent(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59800)
    cc_dir, cx_dir = _agent_dir(tmp_path, "cc"), _agent_dir(tmp_path, "cx")
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", config_dir=cc_dir)
        _register_agent(c, agent_type="codex", config_dir=cx_dir)
        both = _new(
            c,
            {
                "name": "both",
                "protocol": "openai",
                "base_url": "https://gw/v1",
                "anthropic_base_url": "https://gw",
                "secret_value": "sk-both",
            },
        )
        other = _new(c, _anthropic_body(name="other"))
        assert _activate(c, both, "claude_code").status_code == 200
        assert _activate(c, both, "codex").status_code == 200
        codex_before = (cx_dir / "config.toml").read_text()

        # Claude Code moves to another connection; Codex is on `both` still.
        assert _activate(c, other, "claude_code").status_code == 200
        assert _connection_of(c, "claude_code") == other
        assert _connection_of(c, "codex") == both
        assert (cx_dir / "config.toml").read_text() == codex_before


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a connection the agent is not reached by is refused",
)
def test_a_connection_that_does_not_reach_the_agent_is_refused(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59810)
    cx_dir = _agent_dir(tmp_path, "cx")
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", config_dir=_agent_dir(tmp_path, "cc"))
        _register_agent(c, agent_type="codex", config_dir=cx_dir)
        # An Anthropic connection has no OpenAI address for Codex.
        uid = _new(c, _anthropic_body())
        r = _activate(c, uid, "codex")
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "PROVIDER_DOES_NOT_REACH_AGENT"
        assert not (cx_dir / "config.toml").exists()
        assert _connection_of(c, "codex") is None


def test_an_unregistered_agent_cannot_be_switched(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59815)
    with _client(app) as c:
        uid = _new(c, _anthropic_body())
        assert _activate(c, uid, "codex").status_code == 404


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="switching preserves unrelated native-config keys and writes a .bak backup",
)
def test_switch_preserves_keys_and_backs_up(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59820)
    cfg = _agent_dir(tmp_path)
    (cfg / "settings.json").write_text(json.dumps({"theme": "dark"}))
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", config_dir=cfg)
        uid = _new(c, _anthropic_body())
        _activate(c, uid)
        data = json.loads((cfg / "settings.json").read_text())
        assert data["theme"] == "dark"  # unrelated key preserved
        _assert_proxy_form(data)
        assert ConfigFileStore().latest_backup(cfg / "settings.json") is not None  # prior backed up
        assert not (cfg / "settings.json.bak").exists()  # nothing beside the file


@pytest.mark.acceptance(
    spec="provider-switching", scenario="a provider switch is recorded in the audit log"
)
def test_switch_is_audited(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59830)
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", config_dir=_agent_dir(tmp_path))
        uid = _new(c, _anthropic_body())
        _activate(c, uid)
        r = c.get("/api/v1/audit", params={"event_type": "provider_switched"})
        assert r.status_code == 200
        assert "provider_switched" in r.text
        # The entry names the connection by the LABEL it carried at the time —
        # that is what an audit row is for, and it is why the row is found by
        # the resource's uid rather than by that string.
        assert "acme" in r.text


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="route an openai-compatible connection to Claude Code with its scope",
)
def test_openai_connection_scoped_to_claude_code(tmp_path, monkeypatch):
    # The agnes case: an openai-wire gateway the user routes to Claude Code. The
    # projection writer is chosen by AGENT type, so it writes Claude's settings.json
    # (anthropic shape) with the proxy-token apiKeyHelper, and the model proxy
    # routes the agent to THIS connection with its key — per connection, never by
    # a wire+active guess. The routing is a
    # scope edit through the framework's shared surface (ADR per-agent-resource-scope),
    # not a field on the connection; the scope names the AGENT by uid, and
    # ``compatible_agents`` reports back the agent TYPES that resolves to.
    app = _app(tmp_path, monkeypatch, 59890)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        cc = _register_agent(c, agent_type="claude_code", config_dir=cfg)
        r = c.post(
            "/api/v1/providers",
            json={
                "name": "agnes",
                "protocol": "openai",
                "base_url": "https://agnes/v1",
                "anthropic_base_url": "https://agnes",
                "secret_value": "sk-agnes",
            },
        )
        assert r.status_code == 201, r.text
        uid = r.json()["uid"]
        assert r.json()["anthropic_base_url"] == "https://agnes"
        assert r.json()["served_agents"] == ["claude_code", "codex"]
        assert r.json()["compatible_agents"] == ["claude_code", "codex"]

        act = _activate(c, uid)
        assert act.status_code == 200, act.text
        assert act.json()["agent"] == "claude-code"
        data = json.loads((cfg / "settings.json").read_text())
        _assert_proxy_form(data)
        # The proxy relays Claude Code's requests to agnes, with agnes's key.
        assert _route_keys(c)[cc] == (uid, "sk-agnes")


def _store_retired_protocol(tmp_path: pathlib.Path) -> pathlib.Path:
    """A connection file that holds the retired ``ollama`` protocol, keyless as
    it was written before the protocol stopped being offered."""
    from coffer.infrastructure.vault.instance import vault_writer

    [path] = (tmp_path / ".coffer" / "vault" / "resources" / "provider").glob("*.json")
    doc = json.loads(path.read_text())
    doc["config"]["protocol"] = "ollama"
    doc["config"]["secret_ref"] = None
    path.write_text(json.dumps(doc, indent=2) + "\n")
    vault_writer().settle([f"resources/provider/{path.name}"])
    return path


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="refuse to create a connection on the ollama protocol",
)
def test_creating_an_ollama_connection_is_refused(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59850)
    with _client(app) as c:
        r = c.post(
            "/api/v1/providers",
            json={
                "name": "local-llama",
                "protocol": "ollama",
                "base_url": "http://localhost:11434",
            },
        )
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "PROVIDER_PROTOCOL_RETIRED"
        assert c.get("/api/v1/providers").json()["providers"] == []


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="refuse to move a connection onto the ollama protocol",
)
def test_moving_a_connection_onto_ollama_is_refused(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59852)
    with _client(app) as c:
        uid = _new(c, _anthropic_body())
        r = c.patch(f"/api/v1/providers/{uid}", json={"protocol": "ollama"})
        assert r.status_code == 422, r.text
        assert r.json()["error"]["code"] == "PROVIDER_PROTOCOL_RETIRED"
        assert c.get(f"/api/v1/providers/{uid}").json()["protocol"] == "anthropic"


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a stored ollama connection stays readable and deletable",
)
def test_a_stored_ollama_connection_is_listed_and_deleted(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59854)
    with _client(app) as c:
        uid = _new(c, _anthropic_body(name="local-llama"))
        _store_retired_protocol(tmp_path)

        [row] = c.get("/api/v1/providers").json()["providers"]
        assert row["uid"] == uid and row["protocol"] == "ollama"
        assert row["compatible_agents"] == []
        assert c.get(f"/api/v1/providers/{uid}").json()["protocol"] == "ollama"

        # Re-sending the stored wire is not a move.
        same = c.patch(f"/api/v1/providers/{uid}", json={"protocol": "ollama"})
        assert same.status_code == 200, same.text

        assert c.delete(f"/api/v1/providers/{uid}").status_code == 204
        assert c.get("/api/v1/providers").json()["providers"] == []


@pytest.mark.acceptance(
    spec="provider-switching", scenario="activating an ollama connection writes no native config"
)
def test_activating_an_ollama_connection_is_refused_and_writes_nothing(tmp_path, monkeypatch):
    """A stored ollama connection reaches no agent: with a registered Claude
    Code agent, switching it on writes no native config, never becomes
    the agent's connection, and says so rather than reporting a switch that did
    not happen."""
    app = _app(tmp_path, monkeypatch, 59855)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", config_dir=cfg)
        uid = _new(c, _anthropic_body(name="local-llama"))
        _store_retired_protocol(tmp_path)

        act = _activate(c, uid)
        assert act.status_code == 422, act.text
        assert act.json()["error"]["code"] == "PROVIDER_PROTOCOL_RETIRED"
        assert "local-llama" in act.json()["error"]["message"]

        row = c.get(f"/api/v1/providers/{uid}").json()
        assert _connection_of(c, "claude_code") is None
        assert row["compatible_agents"] == []
        assert not (cfg / "settings.json").exists()


@pytest.mark.asyncio
async def test_a_second_transcribe_default_cannot_be_written_behind_the_service(
    tmp_path, monkeypatch
):
    """The single-transcribe-default invariant is enforced by the vault, not
    only by ``set_transcribe_default``.

    A live vault was found with two connections flagged, because the flag is an
    ordinary config field and a write that goes round the service sets it
    without clearing anything. The vault's validator refuses any commit that
    would leave two, whatever writes it: here a hand edit of the second
    connection's file, which stays uncommitted and flagged while ``HEAD`` keeps
    one default.
    """
    from coffer.domain.vault.findings import FindingCode
    from coffer.infrastructure.vault.home import vault_root
    from coffer.infrastructure.vault.instance import vault_writer

    app = _app(tmp_path, monkeypatch, 59872)
    with _client(app) as c:
        first = _new(c, _anthropic_body(name="first"))
        _new(
            c,
            {
                "name": "second",
                "protocol": "openai",
                "base_url": "https://gw/v1",
                "secret_value": "sk-2",
            },
        )
        c.post(f"/api/v1/providers/{first}/transcribe-default")

        path = "resources/provider/second.json"
        doc = json.loads((vault_root() / path).read_text())
        doc["config"]["transcribe_default"] = True
        (vault_root() / path).write_text(json.dumps(doc, indent=2) + "\n")
        vault_writer().settle([path])

        codes = [f.code for f in vault_writer().problems()[path]]
        assert codes == [FindingCode.CONFIG_INVALID]
        head = json.loads(vault_writer().repo.read("HEAD", path) or b"{}")
        assert head["config"].get("transcribe_default") is not True
        listed = c.get("/api/v1/providers").json()["providers"]
        flagged = [p["name"] for p in listed if p["transcribe_default"]]
        assert flagged == ["first"]


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="switch off and re-time the passes Coffer runs unattended",
)
async def test_upkeep_switches_and_intervals_round_trip(tmp_path, monkeypatch):
    """The two timed passes Coffer runs on its own behalf, made visible."""
    from httpx import ASGITransport, AsyncClient

    app = _app(tmp_path, monkeypatch, 59884)
    set_active_token(TOKEN)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": TOKEN}
        ) as c,
    ):
        # Out of the box every pass runs — each writes only derived files — and
        # none has a chosen interval, so each reports the default it actually
        # runs at.
        upkeep = (await c.get("/api/v1/internal-engine-config")).json()["upkeep"]
        assert [upkeep[k]["enabled"] for k in ("aggregate", "distil")] == [True, True]
        assert all(upkeep[k]["interval_s"] is None for k in upkeep)
        assert upkeep["aggregate"]["default_interval_s"] == 3600

        # One pass at a time, and each half independent of the other.
        r = await c.put(
            "/api/v1/internal-engine-config/upkeep", json={"pass": "distil", "enabled": False}
        )
        assert r.status_code == 200, r.text
        assert r.json()["upkeep"]["distil"]["enabled"] is False

        r = await c.put(
            "/api/v1/internal-engine-config/upkeep",
            json={"pass": "aggregate", "interval_s": 900},
        )
        assert r.json()["upkeep"]["aggregate"]["interval_s"] == 900
        # ...and the pass it did not name is exactly as it was left.
        assert r.json()["upkeep"]["distil"]["enabled"] is False

        # Back to the pass's own interval — which a null cannot say.
        r = await c.put(
            "/api/v1/internal-engine-config/upkeep",
            json={"pass": "aggregate", "use_default_interval": True},
        )
        assert r.json()["upkeep"]["aggregate"]["interval_s"] is None

        # A pass this vault does not run is a 422, not a silently ignored write.
        r = await c.put("/api/v1/internal-engine-config/upkeep", json={"pass": "vacuum"})
        assert r.status_code == 422, r.text

        # And an interval below the floor is refused rather than busy-looping
        # the model over the user's files.
        r = await c.put(
            "/api/v1/internal-engine-config/upkeep",
            json={"pass": "aggregate", "interval_s": 5},
        )
        assert r.status_code == 422, r.text


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="curate which of a connection's models are offered downstream",
)
def test_curated_models_round_trip(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59890)
    with _client(app) as c:
        r = c.post(
            "/api/v1/providers",
            json=_anthropic_body(
                name="curated",
                models=[
                    {"id": "opus"},
                    {"id": "sonnet", "modality": "text"},
                    {"id": "opus"},
                    {"id": "embed-1", "modality": "embedding"},
                ],
            ),
        )
        assert r.status_code == 201, r.text
        uid = r.json()["uid"]
        # Stored verbatim (opaque ids), deduped, in the order the user chose,
        # each keeping the kind it was sent as — an entry that named none is
        # ``text``, the kind every curated set held before modalities existed.
        unknown = {
            "context_window": None,
            "user_context_window": None,
            "price": None,
        }
        curated_set = [
            {"id": "opus", "modality": "text", **unknown},
            {"id": "sonnet", "modality": "text", **unknown},
            {"id": "embed-1", "modality": "embedding", **unknown},
        ]
        assert r.json()["models"] == curated_set
        # Survives a re-read and the list route.
        assert c.get(f"/api/v1/providers/{uid}").json()["models"] == curated_set
        listed = {p["uid"]: p["models"] for p in c.get("/api/v1/providers").json()["providers"]}
        assert listed[uid] == curated_set

        # PATCH replaces the whole set (like compatible_agents) — no merging.
        r = c.patch(f"/api/v1/providers/{uid}", json={"models": [{"id": "haiku"}]})
        assert r.status_code == 200, r.text
        assert r.json()["models"] == [{"id": "haiku", "modality": "text", **unknown}]

        # An unrelated PATCH leaves the curated set alone.
        r = c.patch(f"/api/v1/providers/{uid}", json={"base_url": "https://gw/anthropic/v2"})
        assert r.json()["models"] == [{"id": "haiku", "modality": "text", **unknown}]

        # The change rides the resource_updated event a provider update already
        # emits — no event of its own. Asked for by uid, which is what keeps the
        # question "this connection's history" answerable at all.
        events = c.get(
            "/api/v1/audit", params={"resource_uid": uid, "event_type": "resource_updated"}
        ).json()["entries"]
        assert events and events[0]["details"]["after"]["models"] == [
            {"id": "haiku", "modality": "text"}
        ]


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="a connection with no curated models offers every model the endpoint serves",
)
def test_uncurated_connection_is_unrestricted(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59900)
    with _client(app) as c:
        # Created without ``models`` — the default, and what every connection
        # made before this field existed carries.
        r = c.post("/api/v1/providers", json=_anthropic_body(name="open"))
        assert r.status_code == 201, r.text
        uid = r.json()["uid"]
        assert r.json()["models"] == []

        # Curating then clearing with [] returns it to unrestricted.
        r = c.patch(f"/api/v1/providers/{uid}", json={"models": [{"id": "opus"}]})
        assert r.status_code == 200, r.text
        assert r.json()["models"] == [
            {
                "id": "opus",
                "modality": "text",
                "context_window": None,
                "user_context_window": None,
                "price": None,
            }
        ]
        r = c.patch(f"/api/v1/providers/{uid}", json={"models": []})
        assert r.status_code == 200, r.text
        assert r.json()["models"] == []
        assert c.get(f"/api/v1/providers/{uid}").json()["models"] == []


def test_reject_malformed_curated_models(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59910)
    with _client(app) as c:
        r = c.post("/api/v1/providers", json=_anthropic_body(name="bad", models=[{"id": "  "}]))
        assert r.status_code == 422, r.text
        # A modality Coffer does not serve is malformed — unlike an id, the set
        # of kinds is Coffer's own and closed.
        r = c.post(
            "/api/v1/providers",
            json=_anthropic_body(name="odd", models=[{"id": "x", "modality": "hologram"}]),
        )
        assert r.status_code == 422, r.text
        # A model id Coffer has never heard of is NOT malformed — ids are opaque.
        r = c.post(
            "/api/v1/providers", json=_anthropic_body(name="ok", models=[{"id": "who-knows-1"}])
        )
        assert r.status_code == 201, r.text


# -- renaming: a label edit, through the kind-agnostic PATCH ------------------
#
# This kind used to own ``POST /api/v1/providers/{name}/rename``, the only
# rename route of the seven kinds, and it existed because the connection's NAME
# was written into Claude Code's ``settings.json`` and had to be rewritten
# there. The projected helper cites the uid now, so that route is DELETED and
# renaming is a field on ``PATCH /api/v1/resources/{uid}``, the same one every
# kind gets (ADR identity-is-the-uid-inside-the-file). The tests below are
# that route's coverage rewritten against the PATCH — what has to stay true is
# everything the old route worked to preserve.


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="rename a connection and keep its secret, audit trail and projection",
)
def test_rename_keeps_the_uid_secret_and_projection(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59920)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", config_dir=cfg)
        uid = _new(c, _anthropic_body(name="acme"))
        ref_before = _ref_of(c, uid)
        assert _activate(c, uid).status_code == 200
        helper_before = json.loads((cfg / "settings.json").read_text())["apiKeyHelper"]

        r = c.patch(f"/api/v1/resources/{uid}", json={"name": "acme-prod"})
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "acme-prod"
        # The identity did not move, which is the point of the whole change:
        # the PATCH addressed the row by the uid it still carries afterwards,
        # and every URL a client holds goes on working.
        assert r.json()["uid"] == uid
        assert c.get(f"/api/v1/providers/{uid}").json()["name"] == "acme-prod"

        # Only the label moved: the old one resolves to nothing, the new one to
        # this same connection.
        assert _uids_named(c, "acme") == []
        assert _uids_named(c, "acme-prod") == [uid]

        # The vault entry did not move, because it never named the connection:
        # the ref is an address, so a rename has nothing to do to it.
        assert _ref_of(c, uid) == ref_before
        assert _key_present(c, ref_before)

        # And the projection was not rewritten AT ALL — the helper line reads
        # exactly as it did before the rename, because it cites the uid. The
        # deleted rename route existed to rewrite this line; there is nothing
        # left for it to do, which is why the kind stopped needing one.
        data = json.loads((cfg / "settings.json").read_text())
        assert data["apiKeyHelper"] == helper_before
        _assert_proxy_form(data)

        # The trail follows the resource — asking by uid returns the whole
        # history, including the events from before the rename.
        moved = c.get("/api/v1/audit", params={"resource_uid": uid})
        assert moved.status_code == 200, moved.text
        entries = moved.json()["entries"]
        types = {e["event_type"] for e in entries}
        assert {"resource_created", "provider_switched", "resource_renamed"} <= types

        # …and it follows WITHOUT being rewritten: the row that recorded the
        # creation still says the connection was called "acme" then, because it
        # was. Repointing those rows onto the new name used to make the log
        # claim "acme-prod" had been created, which never happened.
        created = next(e for e in entries if e["event_type"] == "resource_created")
        assert created["resource_name"] == "acme"


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="reject a rename onto a name another connection already uses",
)
def test_rename_onto_taken_name_is_rejected(tmp_path, monkeypatch):
    """The label stays unique within the kind although it stopped being the
    identity: two connections called the same thing is something the user
    cannot tell apart, so it is still a 409 — now raised once, in the shared
    PATCH, for every kind rather than in this kind's own route."""
    app = _app(tmp_path, monkeypatch, 59930)
    with _client(app) as c:
        first = _new(c, _anthropic_body(name="first", secret_value="sk-first"))
        second = _new(c, _anthropic_body(name="second", secret_value="sk-second"))

        r = c.patch(f"/api/v1/resources/{first}", json={"name": "second"})
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "RESOURCE_ALREADY_EXISTS"

        # Nothing moved: both connections still carry their own label and their
        # own key, each still reachable at its own uid.
        assert _uids_named(c, "first") == [first]
        assert _uids_named(c, "second") == [second]
        assert _key_present(c, _ref_of(c, first))
        assert _key_present(c, _ref_of(c, second))


def test_renamed_connection_still_serves_its_agent(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59940)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        cc = _register_agent(c, agent_type="claude_code", config_dir=cfg)
        uid = _new(c, _anthropic_body(name="acme", secret_value="sk-the-key"))
        _activate(c, uid)
        before = (cfg / "settings.json").read_text()

        assert c.patch(f"/api/v1/resources/{uid}", json={"name": "acme-2"}).status_code == 200

        # The proxy keeps routing the agent to the same connection and key, and
        # the agent's file — which names only the proxy — did not move at all.
        assert _route_keys(c)[cc] == (uid, "sk-the-key")
        assert (cfg / "settings.json").read_text() == before
        body = c.get(f"/api/v1/providers/{uid}").json()
        assert body["name"] == "acme-2"
        assert _connection_of(c, "claude_code") == uid
        assert "claude_code" in body["compatible_agents"]


def test_rename_to_the_same_name_is_a_noop(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59950)
    with _client(app) as c:
        uid = _new(c, _anthropic_body(name="acme"))
        before = c.get(f"/api/v1/providers/{uid}").json()
        r = c.patch(f"/api/v1/resources/{uid}", json={"name": "acme"})
        assert r.status_code == 200, r.text
        # Nothing moved — not the row (updated_at included), not the vault entry.
        assert c.get(f"/api/v1/providers/{uid}").json() == before
        assert _key_present(c, before["secret_ref"])
        # ...and nothing was recorded either. A client that PATCHes a whole
        # form back sends the label it already has; a trail littered with
        # renames that renamed nothing is worse than no trail.
        silent = c.get(
            "/api/v1/audit", params={"resource_uid": uid, "event_type": "resource_renamed"}
        )
        assert silent.json()["entries"] == []


def test_rename_unknown_connection_is_404(tmp_path, monkeypatch):
    """A uid this vault does not hold is a 404, raised before anything is
    written — the label in the body is never even looked at."""
    app = _app(tmp_path, monkeypatch, 59960)
    with _client(app) as c:
        r = c.patch("/api/v1/resources/0123456789abcdef0123456789abcdef", json={"name": "whatever"})
        assert r.status_code == 404, r.text


# -- per-agent key routing reads the addresses (ADR provider-reach-is-what-its-addresses-serve) --


def test_each_agents_route_follows_the_connection_it_chose(tmp_path, monkeypatch):
    """Two connections, one per agent: the proxy serves each agent the
    connection it chose, with that connection's key — the wrong answer would
    send one agent's traffic on another's key."""
    app = _app(tmp_path, monkeypatch, 59920)
    with _client(app) as c:
        cc = _register_agent(c, agent_type="claude_code", config_dir=_agent_dir(tmp_path, "cc"))
        cx = _register_agent(c, agent_type="codex", config_dir=_agent_dir(tmp_path, "cx"))
        for_claude = _new(c, _anthropic_body("for-claude", secret_value="sk-claude"))
        for_codex = _new(
            c,
            {
                "name": "for-codex",
                "protocol": "openai",
                "base_url": "https://gw/openai",
                "secret_value": "sk-codex",
            },
        )
        assert _activate(c, for_claude).status_code == 200
        assert _activate(c, for_codex, "codex").status_code == 200

        routes = _route_keys(c)
        assert routes[cc] == (for_claude, "sk-claude")
        assert routes[cx] == (for_codex, "sk-codex")


@pytest.mark.acceptance(spec="provider-switching", scenario="a connection cannot be switched off")
def test_a_connection_cannot_be_switched_off(tmp_path, monkeypatch):
    """A connection's switch is retired (ADR
    provider-reach-is-what-its-addresses-serve): the generic disable route
    refuses it and the agent keeps its route."""
    app = _app(tmp_path, monkeypatch, 59930)
    with _client(app) as c:
        cc = _register_agent(c, agent_type="claude_code", config_dir=_agent_dir(tmp_path))
        uid = _new(c, _anthropic_body("acme"))
        assert _activate(c, uid).status_code == 200
        r = c.post(f"/api/v1/resources/{uid}/disable")
        assert r.status_code == 409, r.text
        assert r.json()["error"]["code"] == "RESOURCE_NOT_TOGGLEABLE"
        assert c.post(f"/api/v1/resources/{uid}/enable").status_code == 200
        assert cc in _route_keys(c)


def test_clearing_the_anthropic_address_retires_claude_codes_reach(tmp_path, monkeypatch):
    """Claude Code is reached through the Anthropic address; without it the
    connection serves Codex only, and Claude Code's route leaves the proxy."""
    app = _app(tmp_path, monkeypatch, 59940)
    with _client(app) as c:
        cc = _register_agent(c, agent_type="claude_code", config_dir=_agent_dir(tmp_path))
        uid = _new(
            c,
            {
                "name": "gw",
                "protocol": "openai",
                "base_url": "https://gw/v1",
                "anthropic_base_url": "https://gw",
                "secret_value": "sk-gw",
            },
        )
        assert _activate(c, uid).status_code == 200
        assert cc in _route_keys(c)
        r = c.patch(f"/api/v1/providers/{uid}", json={"anthropic_base_url": ""})
        assert r.status_code == 200, r.text
        assert r.json()["anthropic_base_url"] is None
        assert cc not in _route_keys(c)
        assert c.get(f"/api/v1/providers/{uid}").json()["compatible_agents"] == ["codex"]


async def _flag(uid: str) -> bool:
    """``transcribe_default`` as the connection stores it.

    Read off the service. By uid, like every other read: the service takes no
    label.
    """
    from coffer.domain.provider.config import ProviderConfig
    from coffer.surfaces.http.provider_dependencies import get_provider_service

    cfg = ProviderConfig.model_validate((await get_provider_service().get(uid)).config)
    return cfg.transcribe_default


def test_provider_out_carries_the_resource_title(tmp_path, monkeypatch):
    """spec resource-framework "Carry an optional editable title on the kinds that have one":
    the connection's own read carries the title set through the kind-agnostic
    update, and an empty one clears it back to null."""
    app = _app(tmp_path, monkeypatch, 59795)
    with _client(app) as c:
        uid = _new(c, _anthropic_body())
        assert c.get(f"/api/v1/providers/{uid}").json()["title"] is None

        r = c.patch(f"/api/v1/resources/{uid}", json={"title": "Team gateway"})
        assert r.status_code == 200, r.text
        assert c.get(f"/api/v1/providers/{uid}").json()["title"] == "Team gateway"
        listed = {p["uid"]: p for p in c.get("/api/v1/providers").json()["providers"]}
        assert listed[uid]["title"] == "Team gateway"
        assert listed[uid]["name"] == "acme"

        assert c.patch(f"/api/v1/resources/{uid}", json={"title": ""}).status_code == 200
        assert c.get(f"/api/v1/providers/{uid}").json()["title"] is None


@pytest.mark.acceptance(
    spec="provider-switching", scenario="the Anthropic wire goes to the Anthropic address"
)
def test_each_agent_is_relayed_to_the_address_of_its_wire(tmp_path, monkeypatch):
    """One DeepSeek connection serves both agents (ADR
    one-connection-serves-both-wires): Claude Code's route goes to the
    Anthropic address, Codex's to the base URL."""
    app = _app(tmp_path, monkeypatch, 59960)
    with _client(app) as c:
        cc = _register_agent(c, agent_type="claude_code", config_dir=_agent_dir(tmp_path, "cc"))
        cx = _register_agent(c, agent_type="codex", config_dir=_agent_dir(tmp_path, "cx"))
        uid = _new(
            c,
            {
                "name": "deepseek",
                "protocol": "openai",
                "base_url": "https://api.deepseek.com",
                "anthropic_base_url": "https://api.deepseek.com/anthropic",
                "secret_value": "sk-ds",
            },
        )
        assert c.get(f"/api/v1/providers/{uid}").json()["served_agents"] == [
            "claude_code",
            "codex",
        ]
        assert _activate(c, uid).status_code == 200
        assert _activate(c, uid, "codex").status_code == 200
        roots = {r.agent_uid: r.member.upstream_root for r in _proxy_state(c).routes}
        assert roots[cc] == "https://api.deepseek.com/anthropic"
        assert roots[cx] == "https://api.deepseek.com"
