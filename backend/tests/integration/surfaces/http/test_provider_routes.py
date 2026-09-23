"""End-to-end HTTP coverage for /api/v1/providers/* (spec provider-switching).

Every route under this prefix addresses a connection by its immutable ``uid``
(ADR resource-identity-is-an-immutable-uid). The ``name`` beside it is a label:
these tests assert on it, and resolve *through* it only via the one route that
still finds a resource by label (``_uids_named`` below).
"""

from __future__ import annotations

import json
import pathlib
import tomllib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

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
    return c.get(f"/api/v1/providers/{uid}").json()["credential_ref"]


def _key_present(c, ref: str) -> bool:
    return c.get(f"/api/v1/credentials/{ref}/exists").json()["present"] is True


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


def _register_agent(c: TestClient, *, agent_type: str, name: str, config_dir: pathlib.Path) -> str:
    """Register an agent and return its uid — what a resource scope now holds.

    A scope's ``agents`` list names agent UIDS, not type values: a provider
    scope used to hold type values while other kinds' scopes held names, and
    the uid is the one vocabulary every kind's scope now speaks.
    """
    r = c.post(
        "/api/v1/agents",
        json={"type": agent_type, "name": name, "config_dir": str(config_dir)},
    )
    assert r.status_code == 201, r.text
    return r.json()["uid"]


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
        ref = body["credential_ref"]
        assert ref.startswith("provider/") and "acme" not in ref
        # the secret landed in the vault under that ref
        ex = c.get(f"/api/v1/credentials/{ref}/exists")
        assert ex.status_code == 200 and ex.json()["present"] is True
        # ...but never in the API response
        assert "sk-secret-value" not in r.text


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="create a profile that reuses an existing credential ref",
)
def test_create_reusing_credential_ref(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59720)
    with _client(app) as c:
        c.post("/api/v1/credentials", json={"ref": "shared/key", "value": "sk-shared"})
        r = c.post(
            "/api/v1/providers",
            json={
                "name": "reuse",
                "protocol": "openai",
                "base_url": "https://gw/v1",
                "credential_ref": "shared/key",
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["credential_ref"] == "shared/key"


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
    scenario="reject a profile that supplies neither a secret nor a credential ref",
)
def test_reject_no_credential_source(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59740)
    body = _anthropic_body()
    body.pop("secret_value")
    with _client(app) as c:
        r = c.post("/api/v1/providers", json=body)
        assert r.status_code == 422, r.text
        assert "PROVIDER_CREDENTIAL_SOURCE_INVALID" in r.text


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
    connection and re-entering its key. ``credential_ref`` stays immutable: that
    one IS an address.

    This connection was never switched on, which is the only state the edit is
    free in — a live one is refused (``test_protocol_edit_guard``), because the
    wire decides which agents a connection can cover and which ``use-builtin``
    reverts.
    """
    app = _app(tmp_path, monkeypatch, 59755)
    with _client(app) as c:
        uid = _new(c, _anthropic_body())
        r = c.patch(f"/api/v1/providers/{uid}", json={"protocol": "openai"})
        assert r.status_code == 200, r.text
        assert r.json()["protocol"] == "openai"

        # The one rule the wire still carries: an ollama connection holds no
        # key, so switching a keyed one to it is refused rather than silently
        # orphaning the secret.
        bad = c.patch(f"/api/v1/providers/{uid}", json={"protocol": "ollama"})
        assert bad.status_code == 422, bad.text


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
    scenario="delete a provider profile cleans up its owned credential",
)
def test_delete_cleans_owned_credential(tmp_path, monkeypatch):
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
        _register_agent(c, agent_type="claude_code", name="cc", config_dir=cfg)
        uid = _new(c, _anthropic_body())
        r = c.post(f"/api/v1/providers/{uid}/activate")
        assert r.status_code == 200, r.text
        assert r.json()["projected"] == ["cc"]
        data = json.loads((cfg / "settings.json").read_text())
        # apiKeyHelper cites THIS connection's uid (per-connection key
        # resolution), so the projected agent always reads exactly the
        # activated connection's key — and goes on reading it after the user
        # relabels the connection, which is why this file no longer has to be
        # rewritten on a rename.
        assert data["apiKeyHelper"] == f"coffer provider key --connection-uid {uid}"
        assert data["env"]["ANTHROPIC_BASE_URL"] == "https://gw/anthropic"
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
        cc = _register_agent(c, agent_type="claude_code", name="cc", config_dir=cfg)
        uid = _new(c, _anthropic_body())
        # Bind this agent to its own models; activating projects them (the model
        # lives on the binding, not the connection — spec provider-switching
        # "Take projected model keys from the agent's binding").
        rb = c.patch(
            f"/api/v1/agents/{cc}",
            json={"model": "bound-opus", "fast_model": "bound-haiku"},
        )
        assert rb.status_code == 200, rb.text
        assert rb.json()["model"] == "bound-opus"
        c.post(f"/api/v1/providers/{uid}/activate")
        data = json.loads((cfg / "settings.json").read_text())
        assert data["env"]["ANTHROPIC_MODEL"] == "bound-opus"
        assert data["env"]["ANTHROPIC_SMALL_FAST_MODEL"] == "bound-haiku"


@pytest.mark.acceptance(
    spec="provider-switching", scenario="activate an openai profile writes Codex config"
)
def test_activate_writes_codex_config(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59790)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        cx = _register_agent(c, agent_type="codex", name="cx", config_dir=cfg)
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
        r = c.post(f"/api/v1/providers/{uid}/activate")
        assert r.status_code == 200, r.text
        assert r.json()["projected"] == ["cx"]
        doc = tomllib.loads((cfg / "config.toml").read_text())
        assert doc["model"] == "gpt-x"
        assert doc["model_provider"] == "coffer"
        block = doc["model_providers"]["coffer"]
        assert block["base_url"] == "https://gw/v1"
        assert block["env_key"] == "COFFER_PROVIDER_KEY"


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="switch a wire back to the agent built-in login",
)
def test_use_builtin_removes_projection_and_clears_active(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59785)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", name="cc", config_dir=cfg)
        uid = _new(c, _anthropic_body())
        c.post(f"/api/v1/providers/{uid}/activate")
        # sanity — the connection is projected into the agent config first
        assert json.loads((cfg / "settings.json").read_text())["env"]["ANTHROPIC_BASE_URL"]

        # ``use-builtin`` is addressed by WIRE, not by a connection: it is the
        # agent that is being put back on its own login, and which connection
        # was covering it is what the route answers rather than what it takes.
        r = c.post("/api/v1/providers/use-builtin/anthropic")
        assert r.status_code == 200, r.text
        assert r.json()["deprojected"] == ["cc"]
        # ``previous`` is a LABEL — it is there for a human reading the result,
        # not for addressing anything.
        assert r.json()["previous"] == "acme"

        # projection removed → the agent falls back to its own built-in login
        data = json.loads((cfg / "settings.json").read_text())
        assert "apiKeyHelper" not in data
        assert "ANTHROPIC_BASE_URL" not in data.get("env", {})
        # and the connection is no longer the active override
        providers = c.get("/api/v1/providers").json()["providers"]
        assert all(not p["is_active"] for p in providers)


def test_use_builtin_is_idempotent_noop(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59786)
    with _client(app) as c:
        # Nothing active for the wire → use-builtin is a clean no-op.
        r = c.post("/api/v1/providers/use-builtin/openai")
        assert r.status_code == 200, r.text
        assert r.json()["deprojected"] == []
        assert r.json()["previous"] is None


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="activating a profile deactivates the previous active profile of the same wire format",
)
def test_activate_deactivates_previous(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59800)
    with _client(app) as c:
        first = _new(c, _anthropic_body(name="first"))
        second = _new(c, _anthropic_body(name="second"))
        c.post(f"/api/v1/providers/{first}/activate")
        c.post(f"/api/v1/providers/{second}/activate")
        actives = {p["uid"]: p["is_active"] for p in c.get("/api/v1/providers").json()["providers"]}
        assert actives == {first: False, second: True}


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="activate a profile whose wire matches no registered agent records active but projects nothing",  # noqa: E501
)
def test_activate_without_matching_agent(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59810)
    with _client(app) as c:
        uid = _new(c, _anthropic_body())
        r = c.post(f"/api/v1/providers/{uid}/activate")
        assert r.status_code == 200, r.text
        assert r.json()["projected"] == []
        # A credentialed wire defaults into both agents; neither is registered,
        # so both are skipped. ``skipped`` names agent TYPES — it is telling the
        # user which product received nothing, and a type is not a resource.
        assert r.json()["skipped"] == ["claude_code", "codex"]
        assert c.get(f"/api/v1/providers/{uid}").json()["is_active"] is True


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="switching preserves unrelated native-config keys and writes a .bak backup",
)
def test_switch_preserves_keys_and_backs_up(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59820)
    cfg = _agent_dir(tmp_path)
    (cfg / "settings.json").write_text(json.dumps({"theme": "dark"}))
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", name="cc", config_dir=cfg)
        uid = _new(c, _anthropic_body())
        c.post(f"/api/v1/providers/{uid}/activate")
        data = json.loads((cfg / "settings.json").read_text())
        assert data["theme"] == "dark"  # unrelated key preserved
        assert data["apiKeyHelper"] == f"coffer provider key --connection-uid {uid}"
        assert (cfg / "settings.json.bak").exists()  # prior version backed up


@pytest.mark.acceptance(
    spec="provider-switching", scenario="a provider switch is recorded in the audit log"
)
def test_switch_is_audited(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59830)
    with _client(app) as c:
        uid = _new(c, _anthropic_body())
        c.post(f"/api/v1/providers/{uid}/activate")
        r = c.get("/api/v1/audit", params={"event_type": "provider_switched"})
        assert r.status_code == 200
        assert "provider_switched" in r.text
        # The entry names the connection by the LABEL it carried at the time —
        # that is what an audit row is for, and it is why the row is found by
        # the resource's uid rather than by that string.
        assert "acme" in r.text


@pytest.mark.acceptance(
    spec="provider-switching", scenario="resolve the active provider key for the apiKeyHelper"
)
def test_resolve_active_key(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59840)
    with _client(app) as c:
        uid = _new(c, _anthropic_body(secret_value="sk-the-key"))
        # before activation: no active profile for the wire → 404
        assert c.get("/api/v1/providers/active-key/anthropic").status_code == 404
        c.post(f"/api/v1/providers/{uid}/activate")
        r = c.get("/api/v1/providers/active-key/anthropic")
        assert r.status_code == 200, r.text
        assert r.json()["value"] == "sk-the-key"


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="route an openai-compatible connection to Claude Code with its scope",
)
def test_openai_connection_scoped_to_claude_code(tmp_path, monkeypatch):
    # The agnes case: an openai-wire gateway the user routes to Claude Code. The
    # projection writer is chosen by AGENT type, so it writes Claude's settings.json
    # (anthropic shape) with an apiKeyHelper that cites THIS connection's uid — the
    # key is resolved per-connection, never by a wire+active guess. The routing is a
    # scope edit through the framework's shared surface (ADR per-agent-resource-scope),
    # not a field on the connection; the scope names the AGENT by uid, and
    # ``compatible_agents`` reports back the agent TYPES that resolves to.
    app = _app(tmp_path, monkeypatch, 59890)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        cc = _register_agent(c, agent_type="claude_code", name="cc", config_dir=cfg)
        r = c.post(
            "/api/v1/providers",
            json={
                "name": "agnes",
                "protocol": "openai",
                "base_url": "https://agnes/v1",
                "secret_value": "sk-agnes",
            },
        )
        assert r.status_code == 201, r.text
        uid = r.json()["uid"]
        # A new connection starts on the wire default...
        assert r.json()["compatible_agents"] == ["claude_code", "codex"]
        scoped = c.put(
            f"/api/v1/resources/{uid}/scope",
            json={"scope": {"agents": [cc]}},
        )
        assert scoped.status_code == 200, scoped.text
        # ...and the reported effective set follows the scope.
        assert c.get(f"/api/v1/providers/{uid}").json()["compatible_agents"] == ["claude_code"]

        act = c.post(f"/api/v1/providers/{uid}/activate")
        assert act.status_code == 200, act.text
        assert act.json()["projected"] == ["cc"]
        data = json.loads((cfg / "settings.json").read_text())
        assert data["apiKeyHelper"] == f"coffer provider key --connection-uid {uid}"
        assert data["env"]["ANTHROPIC_BASE_URL"] == "https://agnes/v1"

        # The projected helper fetches exactly agnes's key, by uid.
        key = c.get(f"/api/v1/providers/{uid}/key")
        assert key.status_code == 200, key.text
        assert key.json()["value"] == "sk-agnes"
        # A uid this vault does not hold is a 404.
        assert c.get("/api/v1/providers/0123456789abcdef0123456789abcdef/key").status_code == 404


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="create an ollama connection without a credential",
)
def test_create_ollama_without_credential(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59850)
    with _client(app) as c:
        # ollama has no API key: supply NEITHER secret_value nor credential_ref.
        r = c.post(
            "/api/v1/providers",
            json={
                "name": "local-llama",
                "protocol": "ollama",
                "base_url": "http://localhost:11434",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["protocol"] == "ollama"
        assert body["credential_ref"] is None
        assert body["is_active"] is False  # ollama never projects to an agent
        # Supplying a credential for ollama is rejected.
        r2 = c.post(
            "/api/v1/providers",
            json={
                "name": "bad-ollama",
                "protocol": "ollama",
                "base_url": "http://localhost:11434",
                "secret_value": "nope",
            },
        )
        assert r2.status_code == 422, r2.text


@pytest.mark.acceptance(
    spec="provider-switching", scenario="activating an ollama connection writes no native config"
)
def test_activating_an_ollama_connection_is_refused_and_writes_nothing(tmp_path, monkeypatch):
    """An ollama connection is internal-only: even scoped to a registered
    Claude Code agent, activating it writes no native config, never makes it
    ``is_active``, and says so rather than reporting a switch that did not
    happen."""
    app = _app(tmp_path, monkeypatch, 59855)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        cc = _register_agent(c, agent_type="claude_code", name="cc", config_dir=cfg)
        uid = _new(
            c,
            {"name": "local-llama", "protocol": "ollama", "base_url": "http://localhost:11434"},
        )
        scoped = c.put(f"/api/v1/resources/{uid}/scope", json={"scope": {"agents": [cc]}})
        assert scoped.status_code == 200, scoped.text

        act = c.post(f"/api/v1/providers/{uid}/activate")
        assert act.status_code == 409, act.text
        assert act.json()["error"]["code"] == "PROVIDER_INTERNAL_ONLY"
        assert "local-llama" in act.json()["error"]["message"]

        row = c.get(f"/api/v1/providers/{uid}").json()
        assert row["is_active"] is False
        assert row["compatible_agents"] == []
        assert not (cfg / "settings.json").exists()


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="set a connection as the internal engine default",
)
def test_set_internal_default(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59860)
    with _client(app) as c:
        uid = _new(c, _anthropic_body(name="acme"))
        r = c.post(f"/api/v1/providers/{uid}/internal-default")
        assert r.status_code == 200, r.text
        assert r.json()["internal_default"] is True
        # the flag persists on the connection
        assert c.get(f"/api/v1/providers/{uid}").json()["internal_default"] is True


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="setting a new internal default clears the previous one",
)
def test_set_internal_default_clears_previous(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59870)
    with _client(app) as c:
        first = _new(c, _anthropic_body(name="first"))
        second = _new(
            c,
            {
                "name": "second",
                "protocol": "openai",
                "base_url": "https://gw/v1",
                "secret_value": "sk-2",
            },
        )
        c.post(f"/api/v1/providers/{first}/internal-default")
        assert c.get(f"/api/v1/providers/{first}").json()["internal_default"] is True

        # Switching the default to another connection clears it off the first.
        c.post(f"/api/v1/providers/{second}/internal-default")
        assert c.get(f"/api/v1/providers/{second}").json()["internal_default"] is True
        assert c.get(f"/api/v1/providers/{first}").json()["internal_default"] is False


@pytest.mark.asyncio
async def test_a_second_internal_default_cannot_be_written_behind_the_service(
    tmp_path, monkeypatch
):
    """The single-internal-default invariant is enforced by the DATABASE, not
    only by ``set_internal_default``.

    A live vault was found with two connections flagged, because the flag is an
    ordinary config field and the generic resource-update path writes it without
    clearing anything. A partial unique index makes the second row
    unrepresentable, whatever writes it.

    The raw statements below still go by ``name``: this is reaching BEHIND every
    surface into the table, and the name column is what makes the fixture
    readable there. Nothing about the invariant depends on it — the index is on
    the config flag.
    """
    import sqlite3

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
        c.post(f"/api/v1/providers/{first}/internal-default")

    conn = sqlite3.connect(tmp_path / "c.db")
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE resources SET config_json = "
                "json_set(config_json, '$.internal_default', json('true')) "
                "WHERE kind = 'provider' AND name = 'second'"
            )
        flagged = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM resources WHERE kind = 'provider' "
                "AND json_extract(config_json, '$.internal_default') = 1"
            )
        ]
        assert flagged == ["first"]
    finally:
        conn.close()


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="choose the model the internal engine runs on",
)
async def test_internal_engine_model_overlay(tmp_path, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from coffer.surfaces.http.dependencies import get_audit_service
    from coffer.surfaces.http.engine_config_composition import internal_engine_connection
    from coffer.surfaces.http.provider_dependencies import get_provider_service

    app = _app(tmp_path, monkeypatch, 59880)
    set_active_token(TOKEN)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": TOKEN}
        ) as c,
    ):
        made = await c.post(
            "/api/v1/providers", json=_anthropic_body(name="acme", model="conn-model")
        )
        uid = made.json()["uid"]
        await c.post(f"/api/v1/providers/{uid}/internal-default")

        # Setting the internal-engine model returns it and persists.
        r = await c.put("/api/v1/internal-engine-config", json={"model": "picked-model"})
        assert r.status_code == 200, r.text
        assert r.json()["model"] == "picked-model"
        assert (await c.get("/api/v1/internal-engine-config")).json()["model"] == "picked-model"

        # It is audited as internal_engine_model_set.
        events = await get_audit_service().query(event_type="internal_engine_model_set")
        assert len(events) >= 1

        # The engine's resolution overlays the chosen model onto the flagged
        # connection (whose own model is "conn-model").
        resolved = await internal_engine_connection(get_provider_service()).get_default()
        assert resolved is not None
        assert resolved.model == "picked-model"


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="switch off and re-time the passes Coffer runs unattended",
)
async def test_upkeep_switches_and_intervals_round_trip(tmp_path, monkeypatch):
    """The three passes Coffer runs on its own behalf, made visible.

    Two of them had no switch anywhere, the third's could only be changed by
    hand-editing a synced document, and all three intervals were constants
    compiled into the workers.
    """
    from httpx import ASGITransport, AsyncClient

    app = _app(tmp_path, monkeypatch, 59884)
    set_active_token(TOKEN)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": TOKEN}
        ) as c,
    ):
        # Out of the box every pass runs — each writes only derived files, so
        # none of them is the exception the tidy pass used to be — and none has
        # a chosen interval, so each reports the default it actually runs at.
        upkeep = (await c.get("/api/v1/internal-engine-config")).json()["upkeep"]
        assert [upkeep[k]["enabled"] for k in ("aggregate", "distil", "curate")] == [
            True,
            True,
            True,
        ]
        assert all(upkeep[k]["interval_s"] is None for k in upkeep)
        assert upkeep["aggregate"]["default_interval_s"] == 3600

        # One pass at a time, and each half independent of the other.
        r = await c.put(
            "/api/v1/internal-engine-config/upkeep", json={"pass": "curate", "enabled": False}
        )
        assert r.status_code == 200, r.text
        assert r.json()["upkeep"]["curate"]["enabled"] is False

        r = await c.put(
            "/api/v1/internal-engine-config/upkeep",
            json={"pass": "aggregate", "interval_s": 900},
        )
        assert r.json()["upkeep"]["aggregate"]["interval_s"] == 900
        # ...and the pass it did not name is exactly as it was left.
        assert r.json()["upkeep"]["curate"]["enabled"] is False

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
            json={"pass": "distil", "interval_s": 5},
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
        curated_set = [
            {"id": "opus", "modality": "text"},
            {"id": "sonnet", "modality": "text"},
            {"id": "embed-1", "modality": "embedding"},
        ]
        assert r.json()["models"] == curated_set
        # Survives a re-read and the list route.
        assert c.get(f"/api/v1/providers/{uid}").json()["models"] == curated_set
        listed = {p["uid"]: p["models"] for p in c.get("/api/v1/providers").json()["providers"]}
        assert listed[uid] == curated_set

        # PATCH replaces the whole set (like compatible_agents) — no merging.
        r = c.patch(f"/api/v1/providers/{uid}", json={"models": [{"id": "haiku"}]})
        assert r.status_code == 200, r.text
        assert r.json()["models"] == [{"id": "haiku", "modality": "text"}]

        # An unrelated PATCH leaves the curated set alone.
        r = c.patch(f"/api/v1/providers/{uid}", json={"base_url": "https://gw/anthropic/v2"})
        assert r.json()["models"] == [{"id": "haiku", "modality": "text"}]

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
        assert r.json()["models"] == [{"id": "opus", "modality": "text"}]
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
# kind gets (ADR resource-identity-is-an-immutable-uid). The tests below are
# that route's coverage rewritten against the PATCH — what has to stay true is
# everything the old route worked to preserve.


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="rename a connection and keep its credential, audit trail and projection",
)
def test_rename_keeps_the_uid_credential_and_projection(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59920)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", name="cc", config_dir=cfg)
        uid = _new(c, _anthropic_body(name="acme"))
        ref_before = _ref_of(c, uid)
        assert c.post(f"/api/v1/providers/{uid}/activate").status_code == 200
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
        assert data["apiKeyHelper"] == f"coffer provider key --connection-uid {uid}"

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
        assert c.get(f"/api/v1/providers/{first}/key").json()["value"] == "sk-first"
        assert c.get(f"/api/v1/providers/{second}/key").json()["value"] == "sk-second"


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="an agent bound to a renamed connection still resolves its key",
)
def test_renamed_connection_still_resolves_for_its_agent(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59940)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", name="cc", config_dir=cfg)
        uid = _new(c, _anthropic_body(name="acme", secret_value="sk-the-key"))
        c.post(f"/api/v1/providers/{uid}/activate")

        assert c.patch(f"/api/v1/resources/{uid}", json={"name": "acme-2"}).status_code == 200

        # The key is still resolvable at the same address the agent asks at —
        # the rename never touched it.
        assert c.get(f"/api/v1/providers/{uid}/key").json()["value"] == "sk-the-key"

        # And the command the agent actually shells out to still resolves: take
        # the uid it cites straight out of the written settings.json rather than
        # assuming it, because that file — not this test's variable — is what
        # the agent reads.
        helper = json.loads((cfg / "settings.json").read_text())["apiKeyHelper"]
        cited = helper.rsplit("--connection-uid ", 1)[1].strip()
        assert cited == uid
        key = c.get(f"/api/v1/providers/{cited}/key")
        assert key.status_code == 200, key.text
        assert key.json()["value"] == "sk-the-key"

        # The agent binding is untouched — it is is_active + compatible_agents,
        # not a stored name, so the rename never had to move it.
        body = c.get(f"/api/v1/providers/{uid}").json()
        assert body["name"] == "acme-2"
        assert body["is_active"] is True
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
        assert _key_present(c, before["credential_ref"])
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


# -- per-agent key routing reads the scope (ADR per-agent-resource-scope) ---------------------


@pytest.mark.acceptance(
    spec="provider-switching",
    scenario="per-agent key routing follows the connection's scope",
)
def test_the_key_a_wire_resolves_follows_the_scope(tmp_path, monkeypatch):
    """Two connections, one per agent, told apart by their scope alone.

    This is the routing the migration had to preserve bit-for-bit: before, the
    axis was ``compatible_agents`` inside the config; now it is the resource's
    framework scope, and the wrong answer here means an agent shelling out for
    another agent's key.

    Both agents are REGISTERED here, which they did not have to be before: a
    scope names agents by uid, and only a registered row has one. Writing the
    agent's TYPE value into the scope list was the provider kind's private
    vocabulary — a provider scope then meant something different from a skill
    scope while both were called ``scope.agents`` — and the uid is what
    collapsed the two into one.
    """
    app = _app(tmp_path, monkeypatch, 59920)
    with _client(app) as c:
        cc = _register_agent(
            c, agent_type="claude_code", name="cc", config_dir=_agent_dir(tmp_path, "cc")
        )
        cx = _register_agent(
            c, agent_type="codex", name="cx", config_dir=_agent_dir(tmp_path, "cx")
        )
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
        for uid, agent_uids in ((for_claude, [cc]), (for_codex, [cx])):
            r = c.put(f"/api/v1/resources/{uid}/scope", json={"scope": {"agents": agent_uids}})
            assert r.status_code == 200, r.text
        assert c.post(f"/api/v1/providers/{for_claude}/activate").status_code == 200
        assert c.post(f"/api/v1/providers/{for_codex}/activate").status_code == 200

        # The scope's uids resolve back to agent TYPES on the way out, because
        # that is what a projection is keyed by — one native config file per
        # agent product.
        assert c.get(f"/api/v1/providers/{for_claude}").json()["compatible_agents"] == [
            "claude_code"
        ]
        assert c.get(f"/api/v1/providers/{for_codex}").json()["compatible_agents"] == ["codex"]

        # anthropic stands for Claude Code, openai for Codex.
        assert c.get("/api/v1/providers/active-key/anthropic").json()["value"] == "sk-claude"
        assert c.get("/api/v1/providers/active-key/openai").json()["value"] == "sk-codex"


def test_a_disabled_connection_resolves_no_key_for_its_agent(tmp_path, monkeypatch):
    """``enabled`` is honoured at the projection seam now, so switching a
    connection off stops it answering for its agent even while ``is_active``
    still records that it was the one projected."""
    app = _app(tmp_path, monkeypatch, 59930)
    with _client(app) as c:
        uid = _new(c, _anthropic_body("acme"))
        assert c.post(f"/api/v1/providers/{uid}/activate").status_code == 200
        assert c.get("/api/v1/providers/active-key/anthropic").status_code == 200

        # The switch is the framework's, not this kind's — same route for every
        # kind, addressed by the same uid.
        r = c.post(f"/api/v1/resources/{uid}/disable")
        assert r.status_code == 200, r.text

        assert c.get("/api/v1/providers/active-key/anthropic").status_code == 404


def test_scoping_a_connection_to_no_agent_retires_its_reach(tmp_path, monkeypatch):
    """The dormant case for a connection: an empty agent axis reaches nobody, so
    no agent resolves its key — the same "dormant" meaning every other scoped
    kind has."""
    app = _app(tmp_path, monkeypatch, 59940)
    with _client(app) as c:
        uid = _new(c, _anthropic_body("acme"))
        assert c.post(f"/api/v1/providers/{uid}/activate").status_code == 200

        assert (
            c.put(f"/api/v1/resources/{uid}/scope", json={"scope": {"agents": []}}).status_code
            == 200
        )

        assert c.get("/api/v1/providers/active-key/anthropic").status_code == 404
        assert c.get(f"/api/v1/providers/{uid}").json()["compatible_agents"] == []


async def _flags(uid: str) -> tuple[bool, bool]:
    """``(internal_default, transcribe_default)`` as the connection stores them.

    Read off the service rather than the wire because ``ProviderOut`` reports
    only the internal-engine flag: the transcription one has no page yet, and a
    test that could not see it could not tell "the flag moved" from "the route
    did nothing". By uid, like every other read: the service takes no label.
    """
    from coffer.domain.provider.config import ProviderConfig
    from coffer.surfaces.http.provider_dependencies import get_provider_service

    cfg = ProviderConfig.model_validate((await get_provider_service().get(uid)).config)
    return cfg.internal_default, cfg.transcribe_default


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="bound how long one call to Coffer's own model may take",
)
async def test_model_timeout_is_bounded_and_null_returns_the_default(tmp_path, monkeypatch):
    """The bound on one call to Coffer's own model, chosen and given back.

    Out of range is REFUSED rather than clamped: this is the operator asking
    for a number, and a request silently turned into a different number is
    worse than a rejection they can read. The background passes clamp instead,
    so a row an older build wrote cannot take a pass down.
    """
    from httpx import ASGITransport, AsyncClient

    app = _app(tmp_path, monkeypatch, 59950)
    set_active_token(TOKEN)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": TOKEN}
        ) as c,
    ):
        # Nothing chosen: the row says so, and says what runs meanwhile — so a
        # surface can name the default instead of showing a blank.
        body = (await c.get("/api/v1/internal-engine-config")).json()
        assert body["model_timeout_s"] is None
        assert body["default_model_timeout_s"] == 60

        r = await c.put("/api/v1/internal-engine-config/timeout", json={"seconds": 120})
        assert r.status_code == 200, r.text
        assert r.json()["model_timeout_s"] == 120

        for refused in (1, 6000):
            r = await c.put("/api/v1/internal-engine-config/timeout", json={"seconds": refused})
            assert r.status_code == 422, r.text
        # ...and a refused write left the chosen bound exactly as it stood.
        assert (await c.get("/api/v1/internal-engine-config")).json()["model_timeout_s"] == 120

        # null is the way back to the default, and the only one: the default
        # lives in one place so raising it later reaches every vault that never
        # chose rather than none of them.
        r = await c.put("/api/v1/internal-engine-config/timeout", json={"seconds": None})
        assert r.status_code == 200, r.text
        assert r.json()["model_timeout_s"] is None
        assert r.json()["default_model_timeout_s"] == 60


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="speech-to-text runs on its own connection and its own model",
)
async def test_transcribe_model_is_chosen_and_cleared_by_an_empty_string(tmp_path, monkeypatch):
    """Choosing the speech-to-text model, and stopping transcription.

    Stopping is a real answer rather than a failure: with no model, a turn
    carrying audio hands the agent the file untouched and the recording never
    leaves this machine. An empty string means it as clearly as a null does,
    because a form field a user emptied sends one.
    """
    from httpx import ASGITransport, AsyncClient

    app = _app(tmp_path, monkeypatch, 59960)
    set_active_token(TOKEN)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": TOKEN}
        ) as c,
    ):
        assert (await c.get("/api/v1/internal-engine-config")).json()["transcribe_model"] is None

        r = await c.put(
            "/api/v1/internal-engine-config/transcribe-model", json={"model": "hears-things"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["transcribe_model"] == "hears-things"

        r = await c.put("/api/v1/internal-engine-config/transcribe-model", json={"model": "   "})
        assert r.status_code == 200, r.text
        assert r.json()["transcribe_model"] is None

        await c.put(
            "/api/v1/internal-engine-config/transcribe-model", json={"model": "hears-things"}
        )
        r = await c.put("/api/v1/internal-engine-config/transcribe-model", json={"model": None})
        assert r.json()["transcribe_model"] is None


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="speech-to-text runs on its own connection and its own model",
)
async def test_setting_a_new_transcribe_default_clears_the_previous_one(tmp_path, monkeypatch):
    """At most one connection globally is the one speech is transcribed on."""
    from httpx import ASGITransport, AsyncClient

    app = _app(tmp_path, monkeypatch, 59970)
    set_active_token(TOKEN)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": TOKEN}
        ) as c,
    ):
        first = (await c.post("/api/v1/providers", json=_anthropic_body(name="first"))).json()[
            "uid"
        ]
        second = (
            await c.post(
                "/api/v1/providers",
                json={
                    "name": "second",
                    "protocol": "openai",
                    "base_url": "https://gw/v1",
                    "secret_value": "sk-2",
                },
            )
        ).json()["uid"]

        r = await c.post(f"/api/v1/providers/{first}/transcribe-default")
        assert r.status_code == 200, r.text
        assert await _flags(first) == (False, True)

        r = await c.post(f"/api/v1/providers/{second}/transcribe-default")
        assert r.status_code == 200, r.text
        assert await _flags(second) == (False, True)
        assert await _flags(first) == (False, False)

        # The move is audited under its own event type, so "why is voice going
        # somewhere else" has an answer that names both ends. Both ends are
        # LABELS — the entry is written for a human to read, and the row it
        # belongs to travels as the resource, so the trail survives a rename of
        # either connection.
        events = (
            await c.get("/api/v1/audit", params={"event_type": "provider_transcribe_default_set"})
        ).json()["entries"]
        assert {"from": "first", "to": "second"} in [e["details"] for e in events]

        # A connection this vault does not have is a 404, not a silent no-op.
        assert (
            await c.post("/api/v1/providers/0123456789abcdef0123456789abcdef/transcribe-default")
        ).status_code == 404


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="internal-engine",
    scenario="speech-to-text runs on its own connection and its own model",
)
async def test_the_two_default_flags_never_move_each_other(tmp_path, monkeypatch):
    """Transcription and the internal engine are told apart, both ways.

    They look like one setting and are not: the endpoints serve different
    models, and a gateway that answers chat completions commonly serves no
    ``/audio/transcriptions`` at all. A route that moved both would aim voice
    at a 404 the moment an operator chose an engine.
    """
    from httpx import ASGITransport, AsyncClient

    app = _app(tmp_path, monkeypatch, 59980)
    set_active_token(TOKEN)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": TOKEN}
        ) as c,
    ):
        thinks = (await c.post("/api/v1/providers", json=_anthropic_body(name="thinks"))).json()[
            "uid"
        ]
        hears = (
            await c.post(
                "/api/v1/providers",
                json={
                    "name": "hears",
                    "protocol": "openai",
                    "base_url": "https://gw/v1",
                    "secret_value": "sk-2",
                },
            )
        ).json()["uid"]

        await c.post(f"/api/v1/providers/{thinks}/internal-default")
        await c.post(f"/api/v1/providers/{hears}/transcribe-default")
        assert await _flags(thinks) == (True, False)
        assert await _flags(hears) == (False, True)

        # Re-marking each flag on the connection that already carries the OTHER
        # one leaves that other one alone: the flags are independent, so one
        # connection may carry both without either route touching the twin.
        await c.post(f"/api/v1/providers/{thinks}/transcribe-default")
        assert await _flags(thinks) == (True, True)
        assert await _flags(hears) == (False, False)

        await c.post(f"/api/v1/providers/{hears}/internal-default")
        assert await _flags(hears) == (True, False)
        assert await _flags(thinks) == (False, True)
