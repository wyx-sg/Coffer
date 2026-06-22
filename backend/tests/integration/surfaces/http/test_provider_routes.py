"""End-to-end HTTP coverage for /api/v1/providers/* (spec 011)."""

from __future__ import annotations

import json
import pathlib
import tomllib

import pytest
from starlette.testclient import TestClient

from coffer.surfaces.http.app import create_app
from coffer.surfaces.http.auth import set_active_token

TOKEN = "test-token-011"


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


def _register_agent(c: TestClient, *, agent_type: str, name: str, config_dir: pathlib.Path) -> None:
    r = c.post(
        "/api/v1/agents",
        json={"type": agent_type, "name": name, "config_dir": str(config_dir)},
    )
    assert r.status_code == 201, r.text


def _anthropic_body(name: str = "acme", **over) -> dict:
    body = {
        "name": name,
        "wire_format": "anthropic",
        "base_url": "https://gw/anthropic",
        "model": "claude-opus-4-8",
        "secret_value": "sk-secret-value",
    }
    body.update(over)
    return body


@pytest.mark.acceptance(
    spec="011-provider-switching",
    scenario="create an anthropic provider profile with an inline secret",
)
def test_create_with_inline_secret(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59710)
    with _client(app) as c:
        r = c.post("/api/v1/providers", json=_anthropic_body())
        assert r.status_code == 201, r.text
        assert r.json()["credential_ref"] == "provider/acme/key"
        # the secret landed in the vault under the minted ref
        ex = c.get("/api/v1/credentials/provider/acme/key/exists")
        assert ex.status_code == 200 and ex.json()["present"] is True
        # ...but never in the API response
        assert "sk-secret-value" not in r.text


@pytest.mark.acceptance(
    spec="011-provider-switching",
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
                "wire_format": "openai",
                "base_url": "https://gw/v1",
                "model": "gpt-x",
                "credential_ref": "shared/key",
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["credential_ref"] == "shared/key"


@pytest.mark.acceptance(
    spec="011-provider-switching", scenario="reject a profile with an unknown wire format"
)
def test_reject_unknown_wire_format(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59730)
    with _client(app) as c:
        r = c.post("/api/v1/providers", json=_anthropic_body(wire_format="bogus"))
        assert r.status_code == 422, r.text


@pytest.mark.acceptance(
    spec="011-provider-switching",
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


@pytest.mark.acceptance(spec="011-provider-switching", scenario="update a provider profile")
def test_update_profile(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59750)
    with _client(app) as c:
        c.post("/api/v1/providers", json=_anthropic_body())
        r = c.patch("/api/v1/providers/acme", json={"model": "claude-sonnet-4-6"})
        assert r.status_code == 200, r.text
        assert r.json()["model"] == "claude-sonnet-4-6"


def test_patch_null_fast_model_clears_it(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59755)
    with _client(app) as c:
        c.post("/api/v1/providers", json=_anthropic_body(fast_model="claude-haiku-4-5"))
        assert c.get("/api/v1/providers/acme").json()["fast_model"] == "claude-haiku-4-5"
        r = c.patch("/api/v1/providers/acme", json={"fast_model": None})
        assert r.status_code == 200, r.text
        assert r.json()["fast_model"] is None


@pytest.mark.acceptance(spec="011-provider-switching", scenario="list provider profiles")
def test_list_profiles(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59760)
    with _client(app) as c:
        c.post("/api/v1/providers", json=_anthropic_body(name="a"))
        c.post("/api/v1/providers", json=_anthropic_body(name="b"))
        r = c.get("/api/v1/providers")
        assert r.status_code == 200
        assert {p["name"] for p in r.json()["providers"]} == {"a", "b"}


@pytest.mark.acceptance(
    spec="011-provider-switching",
    scenario="delete a provider profile cleans up its owned credential",
)
def test_delete_cleans_owned_credential(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59770)
    with _client(app) as c:
        c.post("/api/v1/providers", json=_anthropic_body())
        assert c.get("/api/v1/credentials/provider/acme/key/exists").json()["present"] is True
        r = c.delete("/api/v1/providers/acme")
        assert r.status_code == 204, r.text
        assert c.get("/api/v1/credentials/provider/acme/key/exists").json()["present"] is False


@pytest.mark.acceptance(
    spec="011-provider-switching",
    scenario="activate an anthropic profile writes Claude Code settings",
)
def test_activate_writes_claude_settings(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59780)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", name="cc", config_dir=cfg)
        c.post("/api/v1/providers", json=_anthropic_body(fast_model="claude-haiku-4-5"))
        r = c.post("/api/v1/providers/acme/activate")
        assert r.status_code == 200, r.text
        assert r.json()["projected"] == ["cc"]
        data = json.loads((cfg / "settings.json").read_text())
        assert data["apiKeyHelper"] == "coffer provider key --wire anthropic"
        assert data["env"]["ANTHROPIC_BASE_URL"] == "https://gw/anthropic"
        assert data["env"]["ANTHROPIC_MODEL"] == "claude-opus-4-8"
        assert data["env"]["ANTHROPIC_SMALL_FAST_MODEL"] == "claude-haiku-4-5"


@pytest.mark.acceptance(
    spec="011-provider-switching",
    scenario="an agent's model binding overrides the connection model",
)
def test_agent_binding_overrides_connection_model(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59783)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", name="cc", config_dir=cfg)
        c.post("/api/v1/providers", json=_anthropic_body(fast_model="conn-fast"))
        # Bind this agent to its own models; activating re-projects from the binding.
        rb = c.patch(
            "/api/v1/agents/cc",
            json={"model": "bound-opus", "fast_model": "bound-haiku"},
        )
        assert rb.status_code == 200, rb.text
        assert rb.json()["model"] == "bound-opus"
        c.post("/api/v1/providers/acme/activate")
        data = json.loads((cfg / "settings.json").read_text())
        # The agent binding wins over the connection's model/fast_model.
        assert data["env"]["ANTHROPIC_MODEL"] == "bound-opus"
        assert data["env"]["ANTHROPIC_SMALL_FAST_MODEL"] == "bound-haiku"


@pytest.mark.acceptance(
    spec="011-provider-switching", scenario="activate an openai profile writes Codex config"
)
def test_activate_writes_codex_config(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59790)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        _register_agent(c, agent_type="codex", name="cx", config_dir=cfg)
        c.post(
            "/api/v1/providers",
            json={
                "name": "oa",
                "wire_format": "openai",
                "base_url": "https://gw/v1",
                "model": "gpt-x",
                "secret_value": "sk-x",
            },
        )
        r = c.post("/api/v1/providers/oa/activate")
        assert r.status_code == 200, r.text
        assert r.json()["projected"] == ["cx"]
        doc = tomllib.loads((cfg / "config.toml").read_text())
        assert doc["model"] == "gpt-x"
        assert doc["model_provider"] == "coffer"
        block = doc["model_providers"]["coffer"]
        assert block["base_url"] == "https://gw/v1"
        assert block["env_key"] == "COFFER_PROVIDER_KEY"


@pytest.mark.acceptance(
    spec="011-provider-switching",
    scenario="switch a wire back to the agent built-in login",
)
def test_use_builtin_removes_projection_and_clears_active(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59785)
    cfg = _agent_dir(tmp_path)
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", name="cc", config_dir=cfg)
        c.post("/api/v1/providers", json=_anthropic_body(fast_model="claude-haiku-4-5"))
        c.post("/api/v1/providers/acme/activate")
        # sanity — the connection is projected into the agent config first
        assert json.loads((cfg / "settings.json").read_text())["env"]["ANTHROPIC_BASE_URL"]

        r = c.post("/api/v1/providers/use-builtin/anthropic")
        assert r.status_code == 200, r.text
        assert r.json()["deprojected"] == ["cc"]
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
    spec="011-provider-switching",
    scenario="activating a profile deactivates the previous active profile of the same wire format",
)
def test_activate_deactivates_previous(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59800)
    with _client(app) as c:
        c.post("/api/v1/providers", json=_anthropic_body(name="first"))
        c.post("/api/v1/providers", json=_anthropic_body(name="second"))
        c.post("/api/v1/providers/first/activate")
        c.post("/api/v1/providers/second/activate")
        actives = {
            p["name"]: p["is_active"] for p in c.get("/api/v1/providers").json()["providers"]
        }
        assert actives == {"first": False, "second": True}


@pytest.mark.acceptance(
    spec="011-provider-switching",
    scenario="activate a profile whose wire matches no registered agent records active but projects nothing",  # noqa: E501
)
def test_activate_without_matching_agent(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59810)
    with _client(app) as c:
        c.post("/api/v1/providers", json=_anthropic_body())
        r = c.post("/api/v1/providers/acme/activate")
        assert r.status_code == 200, r.text
        assert r.json()["projected"] == []
        assert r.json()["skipped"] == ["claude_code"]
        assert c.get("/api/v1/providers/acme").json()["is_active"] is True


@pytest.mark.acceptance(
    spec="011-provider-switching",
    scenario="switching preserves unrelated native-config keys and writes a .bak backup",
)
def test_switch_preserves_keys_and_backs_up(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59820)
    cfg = _agent_dir(tmp_path)
    (cfg / "settings.json").write_text(json.dumps({"theme": "dark"}))
    with _client(app) as c:
        _register_agent(c, agent_type="claude_code", name="cc", config_dir=cfg)
        c.post("/api/v1/providers", json=_anthropic_body())
        c.post("/api/v1/providers/acme/activate")
        data = json.loads((cfg / "settings.json").read_text())
        assert data["theme"] == "dark"  # unrelated key preserved
        assert data["apiKeyHelper"] == "coffer provider key --wire anthropic"
        assert (cfg / "settings.json.bak").exists()  # prior version backed up


@pytest.mark.acceptance(
    spec="011-provider-switching", scenario="a provider switch is recorded in the audit log"
)
def test_switch_is_audited(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59830)
    with _client(app) as c:
        c.post("/api/v1/providers", json=_anthropic_body())
        c.post("/api/v1/providers/acme/activate")
        r = c.get("/api/v1/audit", params={"event_type": "provider_switched"})
        assert r.status_code == 200
        assert "provider_switched" in r.text
        assert "acme" in r.text


@pytest.mark.acceptance(
    spec="011-provider-switching", scenario="resolve the active provider key for the apiKeyHelper"
)
def test_resolve_active_key(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59840)
    with _client(app) as c:
        c.post("/api/v1/providers", json=_anthropic_body(secret_value="sk-the-key"))
        # before activation: no active profile for the wire → 404
        assert c.get("/api/v1/providers/active-key/anthropic").status_code == 404
        c.post("/api/v1/providers/acme/activate")
        r = c.get("/api/v1/providers/active-key/anthropic")
        assert r.status_code == 200, r.text
        assert r.json()["value"] == "sk-the-key"


@pytest.mark.acceptance(
    spec="011-provider-switching",
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
                "wire_format": "ollama",
                "base_url": "http://localhost:11434",
                "model": "llama3",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["wire_format"] == "ollama"
        assert body["credential_ref"] is None
        assert body["is_active"] is False  # ollama never projects to an agent
        # Supplying a credential for ollama is rejected.
        r2 = c.post(
            "/api/v1/providers",
            json={
                "name": "bad-ollama",
                "wire_format": "ollama",
                "base_url": "http://localhost:11434",
                "model": "llama3",
                "secret_value": "nope",
            },
        )
        assert r2.status_code == 422, r2.text


@pytest.mark.acceptance(
    spec="011-provider-switching",
    scenario="set a connection as the internal engine default",
)
def test_set_internal_default(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59860)
    with _client(app) as c:
        c.post("/api/v1/providers", json=_anthropic_body(name="acme"))
        r = c.post("/api/v1/providers/acme/internal-default")
        assert r.status_code == 200, r.text
        assert r.json()["internal_default"] is True
        # the flag persists on the connection
        assert c.get("/api/v1/providers/acme").json()["internal_default"] is True


@pytest.mark.acceptance(
    spec="011-provider-switching",
    scenario="setting a new internal default clears the previous one",
)
def test_set_internal_default_clears_previous(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, 59870)
    with _client(app) as c:
        c.post("/api/v1/providers", json=_anthropic_body(name="first"))
        c.post(
            "/api/v1/providers",
            json={
                "name": "second",
                "wire_format": "openai",
                "base_url": "https://gw/v1",
                "model": "gpt-x",
                "secret_value": "sk-2",
            },
        )
        c.post("/api/v1/providers/first/internal-default")
        assert c.get("/api/v1/providers/first").json()["internal_default"] is True

        # Switching the default to another connection clears it off the first.
        c.post("/api/v1/providers/second/internal-default")
        assert c.get("/api/v1/providers/second").json()["internal_default"] is True
        assert c.get("/api/v1/providers/first").json()["internal_default"] is False


@pytest.mark.asyncio
@pytest.mark.acceptance(
    spec="011-provider-switching",
    scenario="choose the model the internal engine runs on",
)
async def test_internal_engine_model_overlay(tmp_path, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from coffer.surfaces.http.dependencies import get_audit_service, get_provider_service

    app = _app(tmp_path, monkeypatch, 59880)
    set_active_token(TOKEN)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(
            transport=ASGITransport(app), base_url="http://t", headers={"X-Coffer-Token": TOKEN}
        ) as c,
    ):
        await c.post("/api/v1/providers", json=_anthropic_body(name="acme", model="conn-model"))
        await c.post("/api/v1/providers/acme/internal-default")

        # Setting the internal-engine model returns it and persists.
        r = await c.put("/api/v1/internal-engine-config", json={"model": "picked-model"})
        assert r.status_code == 200, r.text
        assert r.json()["model"] == "picked-model"
        assert (await c.get("/api/v1/internal-engine-config")).json()["model"] == "picked-model"

        # It is audited as internal_engine_model_set.
        events = await get_audit_service().query(event_type="internal_engine_model_set")
        assert len(events) >= 1

        # resolve_internal_connection overlays the chosen model onto the connection
        # (whose own model is "conn-model").
        resolved = await get_provider_service().resolve_internal_connection()
        assert resolved is not None
        assert resolved.model == "picked-model"
